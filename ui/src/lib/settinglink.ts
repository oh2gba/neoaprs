// A text that explains itself by a setting and leads to it: the id of the control (its group is brought into view and flashed, lib/attention.ts) and the hover title of the link.
import { t } from "@/i18n";

export interface SettingLink {
  control: string;
  title: string;
}

/** "RX only: nothing is sent", wherever it is said: it leads to the RX only tickbox, the first row of Settings → Radio. */
export const rxOnlyLink = (): SettingLink => ({ control: "set-station-transmit", title: t("pill.rx_title") });
