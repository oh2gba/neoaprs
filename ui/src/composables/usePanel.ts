// The side panel as the user left it, remembered in the browser (lib/storage.ts): the tab on show, whether it is folded away, and its width.
import { usePersisted, usePersistedFlag, usePersistedNumber } from "@/composables/usePersisted";
import { PANEL_DEFAULT, PANEL_MIN, PANEL_STORED_MAX, TAB_IDS, type TabId } from "@/lib/layout";

export function usePanel() {
  const tab = usePersisted("tab", "stations", TAB_IDS);
  const collapsed = usePersistedFlag("panel", ["collapsed", "open"], false);
  const width = usePersistedNumber("panelwidth", PANEL_DEFAULT, PANEL_MIN, PANEL_STORED_MAX);

  /** Puts a tab in front, the panel unfolded. */
  function show(id: TabId): void {
    tab.value = id;
    collapsed.value = false;
  }

  return { tab, collapsed, width, show };
}

export type Panel = ReturnType<typeof usePanel>;
