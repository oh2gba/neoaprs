// The map controls' labels (zoom buttons, canvas) in the page's language; said again when the
// language changes.
import { watch, type Ref } from "vue";
import { t } from "@/i18n";

export function useMapControlLabels(host: Ref<HTMLElement | null>): () => void {
  function labelControls(): void {
    const label = (selector: string, text: string): void => {
      const el = host.value?.querySelector(selector);
      el?.setAttribute("aria-label", text);
      if (el?.hasAttribute("title")) el.setAttribute("title", text);
    };
    label(".maplibregl-ctrl-zoom-in", t("map.zoom_in"));
    label(".maplibregl-ctrl-zoom-out", t("map.zoom_out"));
    label(".maplibregl-canvas", t("map.label"));
  }
  watch(() => [t("map.zoom_in"), t("map.zoom_out"), t("map.label")], labelControls);
  return labelControls;
}
