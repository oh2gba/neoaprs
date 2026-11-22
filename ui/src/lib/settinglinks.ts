// Settings that belong together: fields sent in one `set_config`, values a choice needs to be
// valid at once, the field a daemon refusal is shown under when it names another setting, and the
// changes that ask first.
import { t } from "@/i18n";
import type { RadioNames } from "@/i18n/errortext";
import { isLoopbackHost } from "@/lib/pagealert";
import { reasonOf } from "@/lib/settings";
import { radioFieldOf } from "@/lib/settingsradio";
import { RADIO_TYPES } from "@/protocol/lists";
import type { ErrorMessage } from "@/protocol/protocol";

/** Where rigctld listens by default (the placeholder of its field). */
const RIGCTLD_DEFAULT = "127.0.0.1:4532";

/**
 * Fields that apply together: leaving one for another of the set waits; leaving the set (or Enter)
 * sends them in one `set_config`.
 */
export const TOGETHER: Record<string, readonly string[]> = {
  "station/lat": ["station/lat", "station/lon"],
  "station/lon": ["station/lat", "station/lon"],
};

/** Every field of every radio type: its key and the set it is sent with (empty for none). */
const RADIO_FIELDS: readonly { key: string; together: string }[] = RADIO_TYPES.flatMap(
  (type): readonly { key: string; together: string }[] => type.fields,
);

/**
 * The fields that apply together with `key`: TOGETHER, or a radio's own fields its type sends
 * together; else `key` alone.
 */
export function togetherOf(key: string): readonly string[] {
  const listed = TOGETHER[key];
  if (listed !== undefined) return listed;
  const own = radioFieldOf(key);
  if (own === null) return [key];
  const pair = RADIO_FIELDS.find((field) => field.key === own.field)?.together ?? "";
  if (pair === "") return [key];
  const fields = [...new Set(RADIO_FIELDS.filter((field) => field.together === pair).map((field) => field.key))];
  return fields.map((field) => `radio/${own.id}/${field}`);
}

/**
 * Whether the daemon's error is shown where it belongs, not in a toast: a setting under its field
 * (useSettingsAnswers), a local-info request in its section (ObjectsQru.vue), a general query in
 * Ask around (NearbyAsk.vue), a radio change under its field (RadioBox.vue).
 */
export const refusedAtField = (error: { cmd: string } | null): boolean =>
  error !== null && ["set_config", "qru_ask", "general_query", "radio_change"].includes(error.cmd);

/**
 * Values that must be sent with the change of `key` to `text` so it is valid at once (a rigctld for
 * the radio status source). `draft` holds the fields.
 */
export function linkedValues(
  key: string,
  text: string,
  draft: Readonly<Record<string, string>>,
): Record<string, string> {
  if (key === "status/source" && text === "rig" && (draft["status/rigctld"] ?? "").trim() === "")
    return { "status/rigctld": RIGCTLD_DEFAULT };
  return {};
}

/**
 * The field a refusal is shown under, and its reason. `error.key` is the setting the daemon names
 * (null for none); `keys` are the settings that were sent. A too-long comment is shown under the
 * power just set, a missing rigctld under the cleared rigctld. `radios` names radios in page words.
 */
export function refusalFor(
  error: Pick<ErrorMessage, "text" | "cmd" | "key" | "code" | "params">,
  keys: readonly string[],
  radios?: RadioNames,
): { key: string; reason: string } {
  const first = keys[0] ?? "";
  const named = error.key;
  const reason = reasonOf(error, radios);
  if (named === null) return { key: first, reason };
  if (keys.includes(named)) return { key: named, reason };
  if (named === "station/comment" && keys.includes("beacon/power_w")) {
    const limit = error.code === "setting.comment_too_long" ? error.params["limit"] : undefined;
    return { key: "beacon/power_w", reason: limit === undefined ? reason : t("settings.shorten_comment", { limit }) };
  }
  if (named === "status/source" && keys.includes("status/rigctld")) return { key: "status/rigctld", reason };
  return { key: first, reason };
}

/**
 * The question to ask before changing `key` to `text`, or null. Only a change that could cut off
 * the device the page is open on (network off, an https switch) asks, on a remote page.
 */
export function confirmMessage(key: string, text: string, remote: boolean): string | null {
  if (!remote) return null;
  if (key === "web/network" && text === "false") return t("settings.confirm.network_off");
  if (key === "web/https") return t(text === "true" ? "settings.confirm.https_on" : "settings.confirm.https_off");
  return null;
}

/** Whether the page is open on another device than the daemon's (not on a loopback address). */
export function remotePage(): boolean {
  return !isLoopbackHost(location.hostname);
}
