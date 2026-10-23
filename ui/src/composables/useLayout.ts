// How the page is laid out for the window it is in (lib/layout.ts: phone, tablet, desktop). On a tablet and a desktop the map and the panel are side by side and this has nothing to decide but how many station cards may be open (`capacity`). A phone shows
// one view at a time: the open tab of the panel (`view` "panel") or the map (`view` "map", the Map button of the tab bar); the view is remembered. What brings the other view:
// - a tab picked in the bar shows the panel (SidePanel does that), and so does anything on the page that asks for a tab (`panel.shown` counts: the unread mail of the header, a card's Message or Edit, the radio state of the header);
// - the first-run guide is on the map, so the map shows while it is open (and the panel is back when it closes);
// - a place to pick on the map (the Beacon tab's Pick on the map, the Objects tab's) shows the map, and when the place is picked, or the picking is cancelled, the tab it came from is back (`picking`);
// - a station picked in the table shows the map with its card (`showMap`).
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
  /** What a phone shows now: the map while the guide is open, else the view the user is in. */
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
  // a window that changes between phone and the others forgets the tab it was to return to
  watch(phone, () => (returnToTab = false));

  /** The classes of the page's root, which style.css and responsive.css go by. */
  const rootClass = computed(() => [`size-${size.value}`, phone.value ? `view-${showing.value}` : "", guideOpen.value ? "guide-open" : ""]);

  return { size, phone, view, showing, capacity, rootClass, showMap: () => (view.value = "map") };
}

export type Layout = ReturnType<typeof useLayout>;
