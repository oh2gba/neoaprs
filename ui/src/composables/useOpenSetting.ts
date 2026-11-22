// "Go to this setting": from a text that names one, open its tab, bring its group into view, flash
// and focus it (lib/attention.ts). Null without a page context: the text is then plain text.
import { inject } from "vue";
import { DAEMON_KEY } from "@/composables/useDaemonContext";
import type { Panel } from "@/composables/usePanel";
import { attend } from "@/lib/attention";
import type { PillTarget } from "@/lib/pills";

export function openSetting(panel: Pick<Panel, "show">, target: PillTarget, control: string): void {
  panel.show(target);
  void attend(control);
}

export function useOpenSetting(): ((target: PillTarget, control: string) => void) | null {
  const context = inject(DAEMON_KEY, null);
  return context === null ? null : (target, control) => openSetting(context.panel, target, control);
}
