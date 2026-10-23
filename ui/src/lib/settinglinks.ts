// How the settings that belong together are handled when they apply as they are changed: the fields that are sent in one `set_config`, the values that go with a choice so that the choice is valid at once, the field a
// refusal of the daemon is shown under when it names another setting than the one that was changed, the changes that ask first, and the words for "<label> changed · Undo".
import { isLoopbackHost } from "@/lib/pagealert";
import { FIELDS, portForProfile, reasonOf } from "@/lib/settings";
import type { ErrorMessage } from "@/protocol/protocol";

/** Where rigctld listens when nobody says otherwise (the placeholder of its field). */
const RIGCTLD_DEFAULT = "127.0.0.1:4532";

/** Fields that apply together: leaving one for another of the set waits, leaving the set (or Enter) sends them in one `set_config`. */
export const TOGETHER: Record<string, readonly string[]> = {
  "station/lat": ["station/lat", "station/lon"],
  "station/lon": ["station/lat", "station/lon"],
  "tcp/host": ["tcp/host", "tcp/port"],
  "tcp/port": ["tcp/host", "tcp/port"],
};

/** What a set of keys changed is called when all of it is changed together. */
const NAMES: { keys: readonly string[]; name: string }[] = [
  { keys: ["station/lat", "station/lon"], name: "Position" },
  { keys: ["tcp/host", "tcp/port"], name: "TCP address" },
  { keys: ["station/symbol_table", "station/symbol_code"], name: "Symbol" },
];

/** The words for a change in the toast that offers to undo it: the group's name when all of a group changed, else the name of the first key. */
export function changeName(keys: readonly string[]): string {
  const group = NAMES.find((n) => n.keys.every((k) => keys.includes(k)));
  if (group) return group.name;
  const first = keys[0] ?? "";
  const info = FIELDS[first];
  return info?.name ?? info?.label ?? first;
}

/** The values that must be sent with the change of `key` to `text` so that the change is valid at once: a serial device does not go with a TCP radio type (the port is cleared), and the radio as the source of the status needs a
 * rigctld (the usual one is filled in). `draft` is what the fields hold. */
export function linkedValues(key: string, text: string, draft: Readonly<Record<string, string>>): Record<string, string> {
  if (key === "tnc/profile") {
    const port = draft["serial/port"] ?? "";
    const kept = portForProfile(text, port);
    return kept === port ? {} : { "serial/port": kept };
  }
  if (key === "status/source" && text === "rig" && (draft["status/rigctld"] ?? "").trim() === "") return { "status/rigctld": RIGCTLD_DEFAULT };
  return {};
}

/** The field a refusal is shown under, and what it says there. `error` is the daemon's `error` for the `set_config` (its `key` is the setting it names, null when it names none, its `code` and `params` say what is wrong), `keys` the
 * settings that were sent. The comment that is too long for the power just set is shown under the power; the radio without a rigctld under the rigctld that was just cleared. */
export function refusalFor(error: Pick<ErrorMessage, "text" | "cmd" | "key" | "code" | "params">, keys: readonly string[]): { key: string; reason: string } {
  const first = keys[0] ?? "";
  const named = error.key;
  const reason = reasonOf(error);
  if (named === null) return { key: first, reason };
  if (keys.includes(named)) return { key: named, reason };
  if (named === "station/comment" && keys.includes("beacon/power_w")) {
    const limit = error.code === "setting.comment_too_long" ? error.params["limit"] : undefined;
    return { key: "beacon/power_w", reason: limit === undefined ? reason : `Shorten the comment to ${limit} first` };
  }
  if (named === "status/source" && keys.includes("status/rigctld")) return { key: "status/rigctld", reason };
  return { key: first, reason };
}

/** The question to ask before the change of `key` to `text` is made, or null when it needs none. A change that would cut off the device the page is open on (the network let in, switched off; an https switch, either way,
 * when there is one) asks first, on a page opened from another device (`remote`); nothing else asks. */
export function confirmMessage(key: string, text: string, remote: boolean): string | null {
  if (!remote) return null;
  if (key === "web/network" && text === "false") return "This device will lose the page. Turn off?";
  if (key === "web/https") return `This device will lose the page. Turn ${text === "true" ? "on" : "off"}?`;
  return null;
}

/** Whether the page is open on another device than the one the daemon runs on (not on a loopback address). */
export function remotePage(): boolean {
  return !isLoopbackHost(location.hostname);
}
