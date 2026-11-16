// The ALOHA circles on the map: their layers made with the others, their lines drawn again when a radius or our position changes, and the radius as the title of the map while the pointer rests on a line. One circle for
// each radio the daemon worked one out for (the topic `map`'s `aloha`: a radio that is on whose type shares a 1200 baud channel, from what that radio heard), each in the map's one look; where radios are named (several
// on) a circle's title names its radio as the page names a radio before its words ("FM 2: ALOHA circle: 42 km").
import { watch, type Ref } from "vue";
import type { GeoJSONSource, MapLayerMouseEvent, Map as MapLibreMap } from "maplibre-gl";
import { formatNumber, t } from "@/i18n";
import { alohaFeatures, type AlohaRing } from "@/lib/alohacircle";
import { ALOHA_HIT, ALOHA_SOURCE, addAlohaLayers } from "@/lib/alohalayers";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { useRadios } from "@/composables/useRadios";

export function useAlohaCircle(
  map: () => MapLibreMap | null,
  host: Ref<HTMLElement | null>,
): { add: (on: MapLibreMap) => void; listen: (on: MapLibreMap) => void } {
  const page = useDaemonContext();
  const radios = useRadios();

  /** "ALOHA circle: 42 km" in the page's language (a tenth of a kilometre below 10 km), after the radio's name where radios are named. */
  function titleOf(radio: number, km: number): string {
    const words = t("map.aloha", { km: formatNumber(km, km < 10 ? 1 : 0) });
    const name = radios.named(radio) ? radios.byId(radio)?.name : undefined;
    return name === undefined ? words : t("radio.line", { name, line: words });
  }
  const rings = (): AlohaRing[] => (page.map.value?.aloha ?? []).map((one) => ({ km: one.km, title: titleOf(one.radio, one.km) }));
  const features = () => alohaFeatures(page.home.value, rings());

  /** The title of the line under the pointer (the first, where lines cross). */
  function hover(event: MapLayerMouseEvent | undefined): void {
    const title: unknown = event?.features?.[0]?.properties?.["title"];
    const text = typeof title === "string" ? title : (rings()[0]?.title ?? "");
    if (text === "") host.value?.removeAttribute("title");
    else host.value?.setAttribute("title", text); // (the tooltip of the browser)
  }

  watch(
    () => [page.home.value?.lat, page.home.value?.lon, JSON.stringify(rings())],
    () => void map()?.getSource<GeoJSONSource>(ALOHA_SOURCE)?.setData(features()),
  );
  return {
    add: (on) => addAlohaLayers(on, features()),
    listen: (on) => {
      on.on("mouseenter", ALOHA_HIT, hover);
      on.on("mousemove", ALOHA_HIT, hover);
      on.on("mouseleave", ALOHA_HIT, () => host.value?.removeAttribute("title"));
    },
  };
}
