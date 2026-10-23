// The map follows what the page picked (components/StationMap.vue): a station picked in the table (`focus`) is flown to, ending clear of the cards over the map, and the marker of a station picked on the map is moved out from under them. Both run after the page is drawn,
// so that the cards are there to keep clear of, and make the map the size of its box first (a phone that has just brought the map back from under the tab).
import { watch } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import type { useClearOfCard } from "@/composables/useClearOfCard";
import type { Focus } from "@/lib/mapview";
import { hasPosition } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

const FLY_ZOOM = 11;

export function useMapFollow(
  map: () => MapLibreMap | null,
  card: ReturnType<typeof useClearOfCard>,
  what: {
    focus: () => Focus | null;
    selected: () => string | null;
    station: (call: string) => StationRow | undefined;
    marker: (call: string) => { lon: number; lat: number } | undefined;
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
}
