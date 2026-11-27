// The settings of a pair of radios in the Digipeater group (neoaprs/pairsetting.py):
// `pair/<low>/<high>/enabled` (the pair passes packets between its radios) and
// `pair/<low>/<high>/ssid` (the SSID of the pair's call). The Call is a choice among free calls:
// not the station's own and not one another enabled pair has; the daemon fills it on first enable.
import { t } from "@/i18n";
import { splitCall } from "@/lib/calls";
import type { FieldInfo } from "@/lib/settings";
import type { Choice } from "@/lib/settingchoices";
import { LIMITS } from "@/protocol/lists";

/**
 * Split `pair/1/2/ssid` into radios 1 and 2 and field `ssid`; null for other keys or radios not in
 * order.
 */
export function pairFieldOf(key: string): { low: number; high: number; field: "enabled" | "ssid" } | null {
  const found = /^pair\/([1-9][0-9]*)\/([1-9][0-9]*)\/(enabled|ssid)$/.exec(key);
  if (found === null) return null;
  const [low, high] = [Number(found[1]), Number(found[2])];
  return low < high ? { low, high, field: found[3] === "ssid" ? "ssid" : "enabled" } : null;
}

/**
 * The SSIDs a pair's Call may take: 15 down to 1, minus the station's and other enabled pairs'; its
 * own value stays.
 */
function freeSsids(key: string, values: Readonly<Record<string, string>>): number[] {
  const station = Number(splitCall(values["station/call"] ?? "").ssid || "0");
  const taken = Object.keys(values).flatMap((other) => {
    const pair = pairFieldOf(other);
    if (pair?.field !== "enabled" || values[other] !== "true") return [];
    const ssidKey = `pair/${pair.low}/${pair.high}/ssid`;
    return ssidKey === key ? [] : [Number(values[ssidKey] ?? "0")];
  });
  const own = Number(values[key] ?? "0");
  const all = Array.from({ length: LIMITS.call.maxSsid }, (_, i) => LIMITS.call.maxSsid - i);
  return all.filter((ssid) => ssid === own || (ssid !== station && !taken.includes(ssid)));
}

/**
 * The Call's choices: each free SSID as the call it makes (`OH2GBA-12`; `-12` with no station
 * call).
 */
const callChoices = (key: string, values: Readonly<Record<string, string>>): Choice[] => {
  const base = splitCall(values["station/call"] ?? "").base;
  return freeSsids(key, values).map((ssid) => ({ value: String(ssid), label: `${base}-${ssid}` }));
};

/** The SSID a pair's key stores, or null for none. */
const storedSsid = (text: string | undefined): number | null => {
  const ssid = Number(text ?? "");
  return Number.isInteger(ssid) && ssid >= 1 && ssid <= LIMITS.call.maxSsid ? ssid : null;
};

/**
 * The SSID a pair has once its Enable is ticked, as the daemon gives it (neoaprs/pairsetting.py
 * `_fill`, held to the vectors `pair_calls`): its stored one while no enabled pair or the station
 * has it, else the highest free one that no disabled pair keeps, else the highest free one.
 */
function ssidOnEnable(key: string, values: Readonly<Record<string, string>>): number | null {
  const own = storedSsid(values[key]);
  const taken = new Set([Number(splitCall(values["station/call"] ?? "").ssid || "0")]);
  const kept = new Set<number>();
  for (const other of Object.keys(values)) {
    const pair = pairFieldOf(other);
    const ssidKey = pair === null ? "" : `pair/${pair.low}/${pair.high}/ssid`;
    if (pair?.field !== "ssid" || ssidKey === key) continue;
    const ssid = storedSsid(values[other]);
    if (ssid === null) continue;
    (values[`pair/${pair.low}/${pair.high}/enabled`] === "true" ? taken : kept).add(ssid);
  }
  if (own !== null && !taken.has(own)) return own;
  const free = Array.from({ length: LIMITS.call.maxSsid }, (_, i) => LIMITS.call.maxSsid - i).filter(
    (ssid) => !taken.has(ssid),
  );
  return free.find((ssid) => !kept.has(ssid)) ?? free[0] ?? null;
}

/** The pair's call as stations put it in their path: the one it has, or the one its Enable gives it. */
export function pairCall(key: string, values: Readonly<Record<string, string>>): string {
  const ssid = ssidOnEnable(key, values);
  return `${splitCall(values["station/call"] ?? "").base}-${ssid ?? ""}`;
}

/**
 * A pair field's description: Enable is a tickbox with an (i), Call a choice of free calls;
 * undefined for other keys.
 */
export function pairField(key: string, values: Readonly<Record<string, string>>): FieldInfo | undefined {
  const pair = pairFieldOf(key);
  if (pair === null) return undefined;
  if (pair.field === "ssid")
    return { label: t("settings.pair.call"), kind: "choice", choices: callChoices(key, values) };
  return {
    label: t("settings.enable.label"),
    name: t("settings.pair.name"),
    kind: "bool",
    tipLabel: t("settings.pair.tip_label"),
    tip: [t("settings.pair.tip1"), t("settings.pair.tip2")],
  };
}
