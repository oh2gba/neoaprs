// Where our status report comes from, as the Status group of the Beacon tab shows it: nothing, a text of our own, or the frequency and mode of the radio (rigctld). The daemon keeps this in `status/source`;
// while that is empty it is what the other settings say, as the daemon works it out (Config.status_choice of neoaprs/config.py): the radio when `status/rigctld` is set, else the text when there is one, else nothing.

import { t } from "@/i18n";
import { lazyText } from "@/lib/lazytext";

export type StatusSource = "off" | "text" | "rig";

/** The sources the status can come from, each with the words it is shown as. */
export const STATUS_CHOICES: readonly { value: StatusSource; readonly label: string }[] = [
  lazyText({ value: "off" as const }, { label: () => t("settings.status_source.off") }),
  lazyText({ value: "text" as const }, { label: () => t("settings.status_source.text") }),
  lazyText({ value: "rig" as const }, { label: () => t("settings.status_source.rig") }),
];

/** The source the settings (key to text, as a form holds them) make. */
export function statusSource(values: Readonly<Record<string, string>>): StatusSource {
  const chosen = (values["status/source"] ?? "").trim().toLowerCase();
  const known = STATUS_CHOICES.find((c) => c.value === chosen);
  if (known) return known.value;
  if ((values["status/rigctld"] ?? "").trim() !== "") return "rig";
  return (values["station/status"] ?? "").trim() !== "" ? "text" : "off";
}

/** Whether a setting of the Status group is shown for the source: the text for a text, the radio's address and the template for a radio, the interval for either. */
export function statusShown(key: string, source: StatusSource): boolean {
  if (key === "station/status") return source === "text";
  if (key === "status/rigctld" || key === "status/template") return source === "rig";
  if (key === "status/interval_min") return source !== "off";
  return true;
}
