// The map follows what the page picked: a station picked in the table (`focus`) is flown to,
// ending clear of the cards, and the marker of a station picked on the map is moved out from under
// them. Both run after the page is drawn so that the cards are there, and make the map the size of
// its box first. A map that follows us (`follow`, the GPS fix, else null) eases to each new place.
// A digipeater with a range (`circle`) is fitted instead of flown to: the map zooms so that the
// whole circle is in view, whether picked in the table (`focus`) or on its marker (`pick`), ending
// clear of the cards. The fit replaces the flight, and the pan that follows a selection leaves a
// map on its way alone, so the two do not fight. Letting go of the selection moves nothing.
import { watch } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import type { useClearOfCard } from "@/composables/useClearOfCard";
import type { Focus } from "@/lib/mapview";
import type { RangeCircle } from "@/lib/nearby";
import { circleBounds } from "@/lib/rangecircles";
import { hasPosition } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const FLY_ZOOM = 11;
/**
 * Following a moving station: the map eases to each fix in this time (fixes come about once a
 * second).
 */
const FOLLOW_ZOOM = 14;
const FOLLOW_MS = 800;
// Pixels between a range circle and the edge of the map when the map is fitted to it.
const FIT_PADDING = 40;

export function useMapFollow(
  map: () => MapLibreMap | null,
  card: ReturnType<typeof useClearOfCard>,
  what: {
    focus: () => Focus | null;
    selected: () => string | null;
    station: (call: string) => StationRow | undefined;
    marker: (call: string) => { lon: number; lat: number } | undefined;
    follow: () => { lon: number; lat: number } | null;
    pick: () => Focus | null;
    circle: (call: string) => RangeCircle | null;
  },
): void {
  /**
   * Fit the map to the whole circle, `FIT_PADDING` px from the edges. With a card over a corner the
   * circle's middle goes where a flight would put it (`flightOffset`) and the padding grows by that
   * much on both sides.
   */
  function fit(on: MapLibreMap, circle: RangeCircle): void {
    const bounds = circleBounds(circle);
    if (bounds === null) return;
    const offset = card.flightOffset()?.offset;
    const [x, y] = offset ?? [0, 0];
    const across = FIT_PADDING + Math.abs(x);
    const down = FIT_PADDING + Math.abs(y);
    on.fitBounds(bounds, {
      padding: { left: across, right: across, top: down, bottom: down },
      ...(offset ? { offset } : {}),
    });
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
      const circle = pick !== null && what.selected() === pick.call ? what.circle(pick.call) : null;
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
      if (on && at)
        on.easeTo({ center: [at.lon, at.lat], zoom: Math.max(on.getZoom(), FOLLOW_ZOOM), duration: FOLLOW_MS });
    },
    { flush: "post" },
  );
}
