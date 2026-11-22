// The side panel as the user left it, kept in the browser: the tab on show, whether it is folded
// away, and its width. `shown` counts the times the page asked for a tab to be put in front (a
// phone brings the tab then, see useLayout).
import { computed, ref, type Ref } from "vue";
import { usePersisted, usePersistedFlag, usePersistedNumber } from "@/composables/usePersisted";
import { useVisible } from "@/composables/useVisible";
import { PANEL_MIN, PANEL_STORED_MAX, TAB_IDS, defaultPanelWidth, type TabId } from "@/lib/layout";
import { isViewingTab } from "@/lib/unread";

export function usePanel() {
  const tab = usePersisted("tab", TAB_IDS[0], TAB_IDS);
  const collapsed = usePersistedFlag("panel", ["collapsed", "open"], false);
  const width = usePersistedNumber("panelwidth", defaultPanelWidth(window.innerWidth), PANEL_MIN, PANEL_STORED_MAX);
  const phoneShowsPanel: Ref<boolean | null> = ref(null);
  const onScreen = computed(() => phoneShowsPanel.value ?? !collapsed.value);

  const shown = ref(0);

  function show(id: TabId): void {
    tab.value = id;
    collapsed.value = false;
    shown.value += 1;
  }

  return { tab, collapsed, width, shown, show, phoneShowsPanel, onScreen };
}

export type Panel = ReturnType<typeof usePanel>;

/**
 * Whether the tab is in front of the user: the tab on show, the panel on screen, the page visible.
 */
export function useViewing(panel: Panel, id: TabId) {
  const visible = useVisible();
  return computed(() => isViewingTab({ tab: panel.tab.value, onScreen: panel.onScreen.value, visible: visible.value }, id));
}
