// The ALOHA circle on the map: its layers made with the others, its line drawn again when the radius or our position changes, and the radius as the title of the map while the pointer rests on the line.
import { watch, type Ref } from "vue";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { formatNumber, t } from "@/i18n";
import { alohaFeatures } from "@/lib/alohacircle";
import { ALOHA_HIT, ALOHA_SOURCE, addAlohaLayers } from "@/lib/alohalayers";
import { useDaemonContext } from "@/composables/useDaemonContext";

export function useAlohaCircle(
  map: () => MapLibreMap | null,
  host: Ref<HTMLElement | null>,
): { add: (on: MapLibreMap) => void; listen: (on: MapLibreMap) => void } {
  const page = useDaemonContext();
  const km = (): number | null => page.map.value?.aloha_km ?? null;
  const features = () => alohaFeatures(page.home.value, km());

  /** "ALOHA circle: 42 km" in the page's language (a tenth of a kilometre below 10 km); empty while there is no circle. */
  function title(): string {
    const radius = km();
    return radius === null ? "" : t("map.aloha", { km: formatNumber(radius, radius < 10 ? 1 : 0) });
  }

  watch(
    () => [page.home.value?.lat, page.home.value?.lon, km()],
    () => void map()?.getSource<GeoJSONSource>(ALOHA_SOURCE)?.setData(features()),
  );
  return {
    add: (on) => addAlohaLayers(on, features()),
    listen: (on) => {
      on.on("mouseenter", ALOHA_HIT, () => host.value?.setAttribute("title", title())); // (the tooltip of the browser)
      on.on("mouseleave", ALOHA_HIT, () => host.value?.removeAttribute("title"));
    },
  };
}
