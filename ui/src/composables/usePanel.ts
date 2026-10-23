// The side panel as the user left it, remembered in the browser (lib/storage.ts): the tab on show, whether it is folded away, and its width. `shown` counts the times the page asked for a tab to be put in front (a phone, which shows the map or a tab,
// brings the tab then: composables/useLayout.ts).
import { ref } from "vue";
import { usePersisted, usePersistedFlag, usePersistedNumber } from "@/composables/usePersisted";
import { PANEL_MIN, PANEL_STORED_MAX, TAB_IDS, defaultPanelWidth, type TabId } from "@/lib/layout";

export function usePanel() {
  const tab = usePersisted("tab", TAB_IDS[0], TAB_IDS);
  const collapsed = usePersistedFlag("panel", ["collapsed", "open"], false);
  const width = usePersistedNumber("panelwidth", defaultPanelWidth(window.innerWidth), PANEL_MIN, PANEL_STORED_MAX);

  const shown = ref(0);

  /** Puts a tab in front, the panel unfolded. */
  function show(id: TabId): void {
    tab.value = id;
    collapsed.value = false;
    shown.value += 1;
  }

  return { tab, collapsed, width, shown, show };
}

export type Panel = ReturnType<typeof usePanel>;
