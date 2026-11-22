// The options of a serial port in the Settings and My station tabs (the TNC's, the GPS
// receiver's): find automatically (the empty port; "not set" for a port that has no search),
// the ports the system lists, the port the settings name or the search found when the system
// does not list it (a udev link such as /dev/brainbox_3, a by-id name), and "Other..." to type
// a path or a socket address. A port (or sound card: lib/mercury.ts) held by another radio or
// the GPS receiver is greyed with the holder's name ("Mobile: COM3"), as the daemon would
// refuse it; the one in force stays as it is, so a setting that already conflicts still shows.
import { t } from "@/i18n";
import type { Choice } from "@/lib/settingchoices";
import type { PortsMessage } from "@/protocol/protocol";

/** The value of the option that opens a text field; never a port. */
export const PORT_OTHER = "\u0000other";

/**
 * Who holds a device, as an option says it: null while it is free or held by the box's own
 * holder; else the holder's name ("" for a holder the page does not know by name).
 */
export type HolderOf = (heldBy: number | null) => string | null;
/** Nobody holds anything (a box that gives no holder). */
const FREE: HolderOf = () => null;

/**
 * The holders of the box of `own` (a radio's id, 0 for the GPS receiver's port): a device held
 * by another radio is named by that radio's name on the page (one the page does not know is
 * held all the same, without a name), the GPS receiver's by its word.
 */
export function holderOf(own: number, nameOf: (id: number) => string | undefined): HolderOf {
  return (heldBy) =>
    heldBy === null || heldBy === own ? null : heldBy === 0 ? t("gps.label") : (nameOf(heldBy) ?? "");
}

/**
 * A device as an option: greyed with its holder's name while another holds it (its own label
 * alone when the holder has no name here), unless it is the one in force.
 */
export function heldChoice(choice: Choice, heldBy: number | null, holder: HolderOf, current: string): Choice {
  const name = holder(heldBy);
  if (name === null || choice.value === current) return choice;
  return {
    ...choice,
    label: name === "" ? choice.label : t("settings.port.held", { holder: name, port: choice.label }),
    disabled: true,
  };
}

/** The ports the system lists, each with what the system calls it. */
function listedPorts(ports: PortsMessage | null, holder: HolderOf = FREE, current = ""): Choice[] {
  return (ports?.ports ?? []).map((p) =>
    heldChoice(
      {
        value: p.device,
        label:
          p.description && p.description !== "n/a" && p.description !== p.device
            ? `${p.device} - ${p.description}`
            : p.device,
      },
      p.held_by,
      holder,
      current,
    ),
  );
}

/**
 * The options for the port `current` (what the form holds), with `found` the port the last
 * search found. Where the daemon does not search (Windows, macOS) the empty port is "none
 * chosen", and for a port it never searches for (`unset`, the GPS receiver's) it is "not set".
 */
export function portOptions(
  ports: PortsMessage | null,
  current: string,
  found: string,
  unset = false,
  holder: HolderOf = FREE,
): Choice[] {
  const listed = listedPorts(ports, holder, current);
  const empty: Choice = {
    value: "",
    label: unset
      ? t("settings.port.unset")
      : ports?.search === false
        ? t("settings.port.none")
        : t("settings.port.auto"),
  };
  const extra = [current, found]
    .filter((path, i, all) => path !== "" && !listed.some((c) => c.value === path) && all.indexOf(path) === i)
    .map((path) => ({ value: path, label: path }));
  return [empty, ...listed, ...extra, { value: PORT_OTHER, label: t("settings.port.other") }];
}
