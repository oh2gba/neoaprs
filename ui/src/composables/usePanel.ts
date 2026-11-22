// The side panel as the user left it, remembered in the browser (lib/storage.ts): the tab on show, whether it is folded away, and its width. `shown` counts the times the page asked for a tab to be put in front (a phone, which shows the map or a tab,
// brings the tab then: composables/useLayout.ts).
import { computed, ref, type Ref } from "vue";
import { usePersisted, usePersistedFlag, usePersistedNumber } from "@/composables/usePersisted";
import { useVisible } from "@/composables/useVisible";
import { PANEL_MIN, PANEL_STORED_MAX, TAB_IDS, defaultPanelWidth, type TabId } from "@/lib/layout";
import { isViewingTab } from "@/lib/unread";

export function usePanel() {
  const tab = usePersisted("tab", TAB_IDS[0], TAB_IDS);
  const collapsed = usePersistedFlag("panel", ["collapsed", "open"], false);
  const width = usePersistedNumber("panelwidth", defaultPanelWidth(window.innerWidth), PANEL_MIN, PANEL_STORED_MAX);
  /** On a phone, which shows the map or the panel in turns: whether the panel is the one shown (set by composables/useLayout.ts); null elsewhere. */
  const phoneShowsPanel: Ref<boolean | null> = ref(null);
  /** Whether the panel's contents are on screen: on a phone in its turn (a phone has no folded panel), elsewhere while it is not folded away. */
  const onScreen = computed(() => phoneShowsPanel.value ?? !collapsed.value);

  const shown = ref(0);

  /** Puts a tab in front, the panel unfolded. */
  function show(id: TabId): void {
    tab.value = id;
    collapsed.value = false;
    shown.value += 1;
  }

  return { tab, collapsed, width, shown, show, phoneShowsPanel, onScreen };
}

export type Panel = ReturnType<typeof usePanel>;

/** Whether the tab is in front of the user's eyes (lib/unread.ts): the tab on show, the panel on screen, the page visible. */
export function useViewing(panel: Panel, id: TabId) {
  const visible = useVisible();
  return computed(() => isViewingTab({ tab: panel.tab.value, onScreen: panel.onScreen.value, visible: visible.value }, id));
}
