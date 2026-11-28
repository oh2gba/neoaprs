"""The map: each layer of the Layers box ticks on and off and the box keeps still, aircraft glide, an open
card and its trail outlive a hidden tab, and satellite cards stay inside the map and hold together."""

import json
from collections.abc import Iterator
from typing import Any

import pytest

from tests.browser import drive
from tests.browser.drive import HOME
from tests.browser.test_every_screen import findings

# The rows of the Layers box that draw something near the demo's station whenever they are ticked (the
# tracks and the ALOHA circle draw only once stations have moved or been heard enough).
DRAWN = ("grid", "daynight", "satellites", "aircraft", "ships")
# The style layers of a row of the Layers box, by the start of their ids.
STYLE_LAYERS = {"aircraft": "traffic", "ships": "traffic", "satellites": "satellite"}
NEAR = json.dumps({"lat": HOME[0], "lon": HOME[1], "zoom": 9})
WORLD = json.dumps({"lat": 50, "lon": 20, "zoom": 1.2})
STEPS = 40  # the steps of the motion an aircraft is followed for
GLIDES = 0.8  # the share of the steps of its motion in which an aircraft that glides moves
STILL_PX = 0.05  # a step this short is no move
# What the map draws for some layers: each one's visibility and the size of its data
SHOWN = """(layers) => { const m = window.__neoMaps[0];
  return JSON.stringify(m.getStyle().layers.filter(l => layers.some(p => l.id.startsWith(p))).map(l => {
    const source = l.source && m.getSource(l.source); const data = source && source.serialize ? source.serialize().data : null;
    return [l.id, l.layout?.visibility ?? 'visible', typeof data === 'object' && data ? JSON.stringify(data).length : String(data)]; })); }"""
# The aircraft drawn on the map, each with its place on the screen
AIRCRAFT = """() => { const m = window.__neoMaps[0]; const c = m.getCanvas().getBoundingClientRect();
  return m.queryRenderedFeatures({ layers: ['traffic'] }).filter(f => f.properties.layer === 'aircraft')
    .map(f => { const p = m.project(f.geometry.coordinates); return { key: f.properties.key, x: p.x + c.x, y: p.y + c.y }; }); }"""
# A click on a thing of the map through the map's own click, where the thing is drawn at that moment (a moving
# aircraft is gone from a place read a moment before; a card over the map would take a click of the mouse)
CLICK = """([layer, field, value]) => { const m = window.__neoMaps[0];
  const f = m.queryRenderedFeatures({ layers: [layer] }).find(f => f.properties[field] === value);
  const at = f.geometry.coordinates;
  m.fire('click', { point: m.project(at), lngLat: { lng: at[0], lat: at[1] }, originalEvent: new MouseEvent('click') }); }"""
TRAIL = """() => window.__neoMaps[0].querySourceFeatures('traffic-trail').reduce((n, f) =>
  n + (f.geometry.type === 'LineString' ? f.geometry.coordinates.length : f.geometry.type === 'MultiLineString' ? f.geometry.coordinates.flat().length : 0), 0)"""
# Follow one aircraft through the places the page gives the map (each step of its motion, whatever the
# speed of the drawing): each step's length on the screen and the milliseconds since the one before
FOLLOW = """([key, steps]) => new Promise(done => { const m = window.__neoMaps[0]; const source = m.getSource('traffic');
  const set = source.setData.bind(source); let last = null; const out = [];
  source.setData = (data) => { const f = (data.features || []).find(f => f.properties.key === key);
    if (f) { const p = m.project(f.geometry.coordinates); const t = performance.now();
      if (last) out.push([Math.hypot(p.x - last.x, p.y - last.y), t - last.t]);
      last = { x: p.x, y: p.y, t }; if (out.length >= steps) { source.setData = set; done(out); } }
    return set(data); }; })"""


def moving(steps: list[list[float]]) -> float:
    """The share of the steps in which the aircraft moved: a glide moves it at every step, where one that
    jumps from report to report stands still in between (how far a step goes depends on the machine's pace)."""
    return sum(1 for d, _ in steps if d > STILL_PX) / len(steps)


@pytest.fixture(scope="module")
def traffic_demo(tmp_path_factory: pytest.TempPathFactory, browser: Any) -> Iterator[Any]:
    """A daemon whose aircraft and ships come from the made-up traffic."""
    demo = drive.Demo(
        tmp_path_factory.mktemp("browser") / "demo", settings={"map/aircraft": "adsbfi", "map/ships": "fintraffic"}
    )
    demo.prepare()
    try:
        demo.start()
        yield demo
    finally:
        demo.stop()


def open_layers(page: Any) -> None:
    page.locator(".layers-toggle").click()
    page.locator(".layers-box").wait_for()


@pytest.mark.parametrize("width", drive.WIDTHS)
def test_each_layer_ticks_on_and_off_and_nothing_in_the_box_moves(
    browser: Any, traffic_demo: Any, faults: Any, width: int
) -> None:
    found = []
    with drive.opened(browser, traffic_demo.url, faults, width=width, view="map", stored={"mapview": NEAR}) as page:
        open_layers(page)
        rows = page.evaluate("() => [...document.querySelectorAll('.layers-row')].map(r => r.dataset.layer)")
        assert set(DRAWN) <= set(rows), f"the Layers box has {rows}"
        for row in rows:
            tick = page.locator(f".layers-row[data-layer={row}] input")
            prefixes = [STYLE_LAYERS.get(row, row)]
            for _ in range(2):
                before, was = page.evaluate(SHOWN, prefixes), tick.is_checked()
                moved, _came = drive.changes(page, ".layers-box", f".layers-row[data-layer={row}] input", tick.click)
                found += [f"{row}: {c}" for c in moved if c.now is not None]
                stored = page.evaluate("row => localStorage.getItem('NeoAPRS.layer.' + row)", row)
                if stored != ("off" if was else "on"):
                    found.append(f"{row}: ticked {'off' if was else 'on'}, this browser keeps {stored!r}")
                if row in DRAWN:
                    page.wait_for_function(f"([layers, n]) => ({SHOWN})(layers) !== n", arg=[prefixes, before])
    assert not found, f"at {width} px:\n  " + "\n  ".join(found[:20])


def an_aircraft(page: Any) -> dict[str, Any]:
    page.wait_for_function(f"() => ({AIRCRAFT})().length > 0")
    return dict(page.evaluate(AIRCRAFT)[0])


def test_an_aircraft_glides_between_its_reports(browser: Any, traffic_demo: Any, faults: Any) -> None:
    stored = {"mapview": NEAR, "layer.aircraft": "on"}
    with drive.opened(browser, traffic_demo.url, faults, width=1280, stored=stored) as page:
        key = an_aircraft(page)["key"]
        page.evaluate(
            """key => { const m = window.__neoMaps[0]; const f = m.queryRenderedFeatures({ layers: ['traffic'] })
                .find(f => f.properties.key === key); m.jumpTo({ center: f.geometry.coordinates, zoom: 13 }); }""",
            key,
        )
        page.wait_for_function("() => !window.__neoMaps[0].isMoving() && window.__neoMaps[0].loaded()")
        steps = page.evaluate(FOLLOW, [key, STEPS])
    assert sum(d for d, _ in steps) > 0, f"the aircraft {key} was not seen moving: {steps}"
    assert moving(steps) >= GLIDES, f"the aircraft {key} stood still between its reports: {steps}"


def test_an_open_aircraft_card_and_its_trail_outlive_a_hidden_tab(browser: Any, traffic_demo: Any, faults: Any) -> None:
    """(The tab is hidden as the page is told it is: the headless browser has no window to hide.)"""
    stored = {"mapview": NEAR, "layer.aircraft": "on"}
    card = ".layercard:not(.satcard)"
    with drive.opened(browser, traffic_demo.url, faults, width=1280, stored=stored) as page:
        plane = an_aircraft(page)
        page.evaluate(CLICK, ["traffic", "key", plane["key"]])
        page.locator(card).wait_for()
        title = page.locator(card).get_attribute("data-thing")
        page.wait_for_function(f"() => ({TRAIL})() >= 2")
        points = page.evaluate(TRAIL)
        page.evaluate("window.__neoHide(true)")
        page.wait_for_function("() => window.__neoMaps[0].queryRenderedFeatures({ layers: ['traffic'] }).length === 0")
        page.evaluate("window.__neoHide(false)")
        page.wait_for_function(f"() => ({AIRCRAFT})().length > 0")
        drive.settle(page)
        assert page.locator(card).count() == 1, "the card closed while the tab was hidden"
        assert page.locator(card).get_attribute("data-thing") == title
        page.wait_for_function(f"n => ({TRAIL})() >= n", arg=points)


def test_two_satellite_cards_stay_inside_the_map_and_hold_together(browser: Any, demo: Any, faults: Any) -> None:
    stored = {"mapview": WORLD, "layer.satellites": "on"}
    marks = """() => { const m = window.__neoMaps[0]; const c = m.getCanvas().getBoundingClientRect();
      return m.queryRenderedFeatures({ layers: ['satellites'] }).map(f => { const p = m.project(f.geometry.coordinates);
        return { id: f.properties.id, x: p.x + c.x, y: p.y + c.y }; })
        .filter(p => p.x > c.left + 40 && p.x < c.right - 40 && p.y > c.top + 40 && p.y < c.bottom - 40); }"""
    # Where the satellites are depends on the hour: each is brought into the map's middle before its click
    drawn = """() => Object.fromEntries(window.__neoMaps[0].queryRenderedFeatures({ layers: ['satellites'] })
      .map(f => [f.properties.id, f.geometry.coordinates]))"""
    with drive.opened(browser, demo.url, faults, width=1280, stored=stored) as page:
        page.wait_for_function(f"() => Object.keys(({drawn})()).length >= 2")
        places = page.evaluate(drawn)
        for key in sorted(places)[:2]:
            one = int(key)
            page.evaluate("at => window.__neoMaps[0].jumpTo({ center: at })", places[key])
            page.wait_for_function(f"id => ({marks})().some(m => m.id === id)", arg=one)
            page.evaluate(CLICK, ["satellites", "id", one])
            page.wait_for_function("id => document.querySelector(`.satcard[data-satellite='${id}']`)", arg=one)
            drive.settle(page)
        outside = page.evaluate(
            """() => { const map = document.querySelector('.mapwrap').getBoundingClientRect();
              return [...document.querySelectorAll('.layercard')].map(c => c.getBoundingClientRect())
                .filter(r => r.left < map.left - 1 || r.right > map.right + 1 || r.top < map.top - 1 || r.bottom > map.bottom + 1)
                .map(r => `a card at ${Math.round(r.left)}..${Math.round(r.right)} in the map's ${Math.round(map.left)}..${Math.round(map.right)}`); }"""
        )
        found = outside + findings(page, "en")
    assert not found, "\n  ".join(found[:20])
