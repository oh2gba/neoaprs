// The map follows what the page picked (components/StationMap.vue): a station picked in the table (`focus`) is flown to, ending clear of the cards over the map, and the marker of a station picked on the map is moved out from under them. Both run after the page is drawn,
// so that the cards are there to keep clear of, and make the map the size of its box first (a phone that has just brought the map back from under the tab). A map that follows us (`follow`, the place of the GPS fix while the person
// has asked for it, else null) is eased to each new place of it.
import { watch } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import type { useClearOfCard } from "@/composables/useClearOfCard";
import type { Focus } from "@/lib/mapview";
import { hasPosition } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const FLY_ZOOM = 11;
/** Following a moving station: at least this close, and the map eases to each fix in this time (the fixes come about once a second). */
const FOLLOW_ZOOM = 14;
const FOLLOW_MS = 800;

export function useMapFollow(
  map: () => MapLibreMap | null,
  card: ReturnType<typeof useClearOfCard>,
  what: {
    focus: () => Focus | null;
    selected: () => string | null;
    station: (call: string) => StationRow | undefined;
    marker: (call: string) => { lon: number; lat: number } | undefined;
    follow: () => { lon: number; lat: number } | null;
  },
): void {
  watch(
    what.focus,
    (focus) => {
      const row = focus ? what.station(focus.call) : undefined;
      const on = map();
      on?.resize();
      if (on && row && hasPosition(row)) on.flyTo({ center: [row.lon, row.lat], zoom: Math.max(on.getZoom(), FLY_ZOOM), ...card.flightOffset() });
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
