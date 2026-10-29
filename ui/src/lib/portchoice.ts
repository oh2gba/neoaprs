// The options of a serial port in the Settings and My station tabs (the TNC's, the GPS receiver's): find automatically (the empty port; "not set" for a port that has no search), the ports the system lists, the port the settings name or the search found when the system does not list it (a udev link such as /dev/brainbox_3,
// a by-id name), and "Other..." to type a path or a socket address.
import { t } from "@/i18n";
import type { Choice } from "@/lib/settingchoices";
import { portChoices } from "@/lib/setup";
import type { PortsMessage } from "@/protocol/protocol";

/** The value of the option that opens a text field; never a port. */
export const PORT_OTHER = "\u0000other";

/** The options for the port `current` (what the form holds) with `found` the port the search found last. Where the daemon does not search (Windows, macOS) the empty port is "none chosen", and for a port the daemon never searches for (`unset`, the GPS receiver's)
 * it is "not set". */
export function portOptions(ports: PortsMessage | null, current: string, found: string, unset = false): Choice[] {
  const listed = portChoices(ports).slice(1);
  const first: Choice = { value: "", label: unset ? t("settings.port.unset") : ports?.search === false ? t("settings.port.none") : t("settings.port.auto") };
  const extra = [current, found]
    .filter((path, i, all) => path !== "" && !listed.some((c) => c.value === path) && all.indexOf(path) === i)
    .map((path) => ({ value: path, label: path }));
  return [first, ...listed, ...extra, { value: PORT_OTHER, label: t("settings.port.other") }];
}
