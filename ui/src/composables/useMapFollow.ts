// The map follows what the page picked (components/StationMap.vue): a station picked in the table (`focus`) is flown to, ending clear of the cards over the map, and the marker of a station picked on the map is moved out from under them. Both run after the page is drawn,
// so that the cards are there to keep clear of, and make the map the size of its box first (a phone that has just brought the map back from under the tab). A map that follows us (`follow`, the place of the GPS fix while the person
// has asked for it, else null) is eased to each new place of it.
// so that the cards are there to keep clear of, and make the map the size of its box first (a phone that has just brought the map back from under the tab).
// A digipeater that gave a range (`circle`: its range circle, which the map draws while it is selected) is not flown to but fitted: the map zooms in or out so that the whole circle is in view, whether it was picked in the table (`focus`) or by a click on its marker (`pick`),
// ending clear of the cards the same way. Any other station is flown to (the table) or left where it is (the marker) as before. The fit takes the place of the flight, and the pan that follows a selection leaves a map that is on its way alone, so that the two do not fight.
// Letting go of the selection moves nothing.
import { watch } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import type { useClearOfCard } from "@/composables/useClearOfCard";
import type { Focus } from "@/lib/mapview";
import type { RangeCircle } from "@/lib/nearby";
import { circleBounds } from "@/lib/rangecircles";
import { hasPosition } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const FLY_ZOOM = 11;
/** Following a moving station: at least this close, and the map eases to each fix in this time (the fixes come about once a second). */
const FOLLOW_ZOOM = 14;
const FOLLOW_MS = 800;
const FIT_PADDING = 40; // px between a range circle and the edge of the map when the map is fitted to it

export function useMapFollow(
  map: () => MapLibreMap | null,
  card: ReturnType<typeof useClearOfCard>,
  what: {
    focus: () => Focus | null;
    selected: () => string | null;
    station: (call: string) => StationRow | undefined;
    marker: (call: string) => { lon: number; lat: number } | undefined;
    follow: () => { lon: number; lat: number } | null;
    /** The marker that was clicked last (`n` counts up, as `focus` does). */
    pick: () => Focus | null;
    /** The range circle of a station, when it is a digipeater that gave a range and has a position; null for any other. */
    circle: (call: string) => RangeCircle | null;
  },
): void {
  /** The map goes to the whole circle, `FIT_PADDING` px from the edges. With a card over a corner the middle of the circle goes where a flight to a station would put it (`flightOffset`), and the padding grows by that much on both sides, as the fit makes room for the offset only on one. */
  function fit(on: MapLibreMap, circle: RangeCircle): void {
    const bounds = circleBounds(circle);
    if (bounds === null) return;
    const offset = card.flightOffset()?.offset;
    const [x, y] = offset ?? [0, 0];
    const across = FIT_PADDING + Math.abs(x);
    const down = FIT_PADDING + Math.abs(y);
    on.fitBounds(bounds, { padding: { left: across, right: across, top: down, bottom: down }, ...(offset ? { offset } : {}) });
  }

  watch(
    what.focus,
    (focus) => {
      const row = focus ? what.station(focus.call) : undefined;
      const on = map();
      on?.resize();
      if (!on || !focus || !row || !hasPosition(row)) return;
      const circle = what.circle(focus.call);
      if (circle) fit(on, circle);
      else on.flyTo({ center: [row.lon, row.lat], zoom: Math.max(on.getZoom(), FLY_ZOOM), ...card.flightOffset() });
    },
    { flush: "post" },
  );
  watch(
    what.pick,
    (pick) => {
      const on = map();
      on?.resize();
      const circle = pick !== null && what.selected() === pick.call ? what.circle(pick.call) : null; // (a Ctrl+click that closed the card picked nothing)
      if (on && circle) fit(on, circle);
    },
    { flush: "post" },
  );
  watch(
    what.selected,
    (call) => {
      const on = map();
      const one = call === null ? undefined : what.marker(call);
      on?.resize();
      if (on && one) card.panClear(on, one);
    },
    { flush: "post" },
  );
  watch(
    () => {
      const at = what.follow();
      return at && `${at.lat} ${at.lon}`;
    },
    () => {
      const at = what.follow();
      const on = map();
      if (on && at) on.easeTo({ center: [at.lon, at.lat], zoom: Math.max(on.getZoom(), FOLLOW_ZOOM), duration: FOLLOW_MS });
    },
    { flush: "post" },
  );
}
