// A text that explains itself by a setting and leads to it: the tab (null: none, the control is on
// every tab), the id of the control (its group is brought into view and flashed, lib/attention.ts)
// and the hover title of the link.
import { t } from "@/i18n";
import type { PillTarget } from "@/lib/pills";
import { RX_SWITCH_ID } from "@/lib/rxswitch";

export interface SettingLink {
  target: PillTarget | null;
  control: string;
  title: string;
}

/** "RX only: nothing is sent", wherever it is said: it leads to the RX only switch at the top right. */
export const rxOnlyLink = (): SettingLink => ({ target: null, control: RX_SWITCH_ID, title: t("header.rx.rx_title") });
