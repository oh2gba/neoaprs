// How the settings that belong together are handled when they apply as they are changed: the fields that are sent in one `set_config`, the values that go with a choice so that the choice is valid at once, the field a
// refusal of the daemon is shown under when it names another setting than the one that was changed, the changes that ask first.
import { t } from "@/i18n";
import { isLoopbackHost } from "@/lib/pagealert";
import { reasonOf } from "@/lib/settings";
import { portForProfile } from "@/lib/tncprofile";
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

/** Whether the daemon's error is told in the place it is about and in no toast: the refusal of a setting is under its field (useSettingsAnswers), that of a request for local info in the row of its section (NearbyQru.vue). */
export const refusedAtField = (error: { cmd: string } | null): boolean => error !== null && (error.cmd === "set_config" || error.cmd === "qru_ask");

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
    return { key: "beacon/power_w", reason: limit === undefined ? reason : t("settings.shorten_comment", { limit }) };
  }
  if (named === "status/source" && keys.includes("status/rigctld")) return { key: "status/rigctld", reason };
  return { key: first, reason };
}

/** The question to ask before the change of `key` to `text` is made, or null when it needs none. A change that would cut off the device the page is open on (the network let in, switched off; an https switch, either way,
 * when there is one) asks first, on a page opened from another device (`remote`); nothing else asks. */
export function confirmMessage(key: string, text: string, remote: boolean): string | null {
  if (!remote) return null;
  if (key === "web/network" && text === "false") return t("settings.confirm.network_off");
  if (key === "web/https") return t(text === "true" ? "settings.confirm.https_on" : "settings.confirm.https_off");
  return null;
}

/** Whether the page is open on another device than the one the daemon runs on (not on a loopback address). */
export function remotePage(): boolean {
  return !isLoopbackHost(location.hostname);
}
