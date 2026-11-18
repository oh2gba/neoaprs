// The ALOHA circles on the map: their layers made with the others, and their lines drawn again when a radius or our position changes, or the row ALOHA circle of the Layers box is ticked or not (`on`: with it off
// nothing is drawn). One circle for each radio the daemon worked one out for (the topic `map`'s `aloha`: a radio that is on whose type shares a 1200 baud channel, from what that radio heard), each in the map's one
// look. The circle has no title: the box names it, and Statistics, Reach gives each radius.
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
