// The ALOHA circles on the map: one per radio the daemon computed one for (topic `map`, `aloha`),
// drawn again when a radius or our position changes or the Layers row is toggled (`on`).
import { watch } from "vue";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { alohaFeatures } from "@/lib/alohacircle";
import { ALOHA_SOURCE, addAlohaLayers } from "@/lib/alohalayers";
import { useDaemonContext } from "@/composables/useDaemonContext";

export function useAlohaCircle(map: () => MapLibreMap | null, on: () => boolean): { add: (to: MapLibreMap) => void } {
  const page = useDaemonContext();
  const radii = (): number[] => (on() ? (page.map.value?.aloha ?? []).map((one) => one.km) : []);
  const features = () => alohaFeatures(page.home.value, radii());

  watch(
    () => [page.home.value?.lat, page.home.value?.lon, radii().join(" ")],
    () => void map()?.getSource<GeoJSONSource>(ALOHA_SOURCE)?.setData(features()),
  );
  return { add: (to) => addAlohaLayers(to, features()) };
}
