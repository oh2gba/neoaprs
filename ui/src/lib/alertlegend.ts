// The legend of the daemon's own alert box in the Settings tab's Notifications group (`SUBGROUPS`
// of lib/settings.ts). The alert runs on the computer NeoAPRS runs on, whichever device shows the
// page. In the desktop app that computer is the person's; where the window has no alert of its own
// (Linux and Windows, lib/shell.ts `daemonTells`) this is the only box, with no word of a next
// group; on a Mac the next box is the window.
import type { PictureName } from "@/help/names";
import { t } from "@/i18n";
import { daemonTells, inApp } from "@/lib/shell";

export const alertLegend: {
  readonly text: string;
  readonly title: string;
  readonly tipLabel: string;
  readonly tip: readonly string[];
  readonly picture: PictureName;
} = {
  get text() {
    return t(inApp() ? "settings.alerts.text_app" : "settings.alerts.text");
  },
  get title() {
    return t(inApp() ? "settings.alerts.title_app" : "settings.alerts.title");
  },
  get tipLabel() {
    return t("settings.alerts.tip_label");
  },
  get tip() {
    return [
      t(inApp() ? "settings.alerts.tip1_app" : "settings.alerts.tip1"),
      ...(daemonTells() ? [] : [t(inApp() ? "settings.alerts.tip2_app" : "settings.alerts.tip2")]),
    ];
  },
  picture: "notifications",
};
