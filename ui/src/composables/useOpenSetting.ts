// "Go to this setting": from a text that names one (the line "RX only: nothing is sent", the toast that says the same), open the tab it is in and bring its group into view, flash it and focus it (lib/attention.ts), as the marks of the header do.
// Null where the page has no context to take the panel from (a pane mounted alone): the text is then plain text.
import { inject } from "vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import type { Panel } from "@/composables/usePanel";
import { attend } from "@/lib/attention";
import type { PillTarget } from "@/lib/pills";

/** The tab `target` in front, and the group of the control with this id brought into view and flashed. */
export function openSetting(panel: Pick<Panel, "show">, target: PillTarget, control: string): void {
  panel.show(target);
  void attend(control);
}

/** The function that goes to a setting, for the page's panel; null when there is no page context. */
export function useOpenSetting(): ((target: PillTarget, control: string) => void) | null {
  const context = inject(DAEMON_KEY, null);
  return context === null ? null : (target, control) => openSetting(context.panel, target, control);
}
