// How the page is laid out for the window (phone, tablet, desktop). Tablet and desktop show map
// and panel side by side; only the card `capacity` is decided here. A phone shows one view at a
// time, `view` "panel" or "map", and remembers it. The other view is brought up by:
// - a tab picked in the bar, or anything asking for a tab (`panel.shown`);
// - the first-run guide, which is on the map;
// - a place to pick on the map; when picked or cancelled, the tab it came from returns (`picking`);
// - a station picked in the table (`showMap`).
import { computed, watch, type Ref } from "vue";
import { usePersisted } from "@/composables/usePersisted";
import type { Panel } from "@/composables/usePanel";
import { useViewport } from "@/composables/useViewport";
import { cardCapacity } from "@/lib/layout";

export type PhoneView = "map" | "panel";
const VIEWS = ["map", "panel"] as const;

export function useLayout(panel: Panel, guideOpen: Readonly<Ref<boolean>>, picking: Readonly<Ref<boolean>>) {
  const { size } = useViewport();
  const view = usePersisted<PhoneView>("view", "map", VIEWS);
  const phone = computed(() => size.value === "phone");
  const showing = computed<PhoneView>(() => (guideOpen.value ? "map" : view.value));
  const capacity = computed(() => cardCapacity(size.value));

  let returnToTab = false;
  watch(picking, (on) => {
    if (!phone.value) return;
    if (on) {
      returnToTab = view.value === "panel";
      view.value = "map";
    } else if (returnToTab) {
      returnToTab = false;
      view.value = "panel";
    }
  });
  watch(
    () => panel.shown.value,
    () => (view.value = "panel"),
  );
  // A window that changes between phone and the others forgets the tab to return to.
  watch(phone, () => (returnToTab = false));
  watch([phone, showing], ([isPhone, now]) => (panel.phoneShowsPanel.value = isPhone ? now === "panel" : null), {
    immediate: true,
    flush: "sync",
  });

  const rootClass = computed(() => [
    `size-${size.value}`,
    phone.value ? `view-${showing.value}` : "",
    guideOpen.value ? "guide-open" : "",
  ]);

  return { size, phone, view, showing, capacity, rootClass, showMap: () => (view.value = "map") };
}

export type Layout = ReturnType<typeof useLayout>;
