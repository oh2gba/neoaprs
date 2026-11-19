// The settings of a pair of radios in the Digipeater group (neoaprs/pairsetting.py): `pair/<low>/<high>/enabled`, whether the pair passes packets between its two radios, and `pair/<low>/<high>/ssid`, the SSID of
// the pair's call on the station's base call. The Call is a choice of the calls that are free: never the station's own, never one another pair that is on has; the daemon fills it when the pair is first switched on.
import { t } from "@/i18n";
import { splitCall } from "@/lib/calls";
import type { FieldInfo } from "@/lib/settings";
import type { Choice } from "@/lib/settingchoices";
import { LIMITS } from "@/protocol/lists";

/** The radios and the field of a pair's setting: `pair/1/2/ssid` is radios 1 and 2's `ssid`; null for any other key (and for one whose radios are not in order). */
export function pairFieldOf(key: string): { low: number; high: number; field: "enabled" | "ssid" } | null {
  const found = /^pair\/([1-9][0-9]*)\/([1-9][0-9]*)\/(enabled|ssid)$/.exec(key);
  if (found === null) return null;
  const [low, high] = [Number(found[1]), Number(found[2])];
  return low < high ? { low, high, field: found[3] === "ssid" ? "ssid" : "enabled" } : null;
}

/** The SSIDs a pair's Call may be in these values: 15 down to 1, without the station's own and those of the other pairs that are on; its own value always among them. */
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

/** The Call's choices: each free SSID as the call it makes (`OH2GBA-12`; `-12` while the station has no call). */
const callChoices = (key: string, values: Readonly<Record<string, string>>): Choice[] => {
  const base = splitCall(values["station/call"] ?? "").base;
  return freeSsids(key, values).map((ssid) => ({ value: String(ssid), label: `${base}-${ssid}` }));
};

/** What a pair's field says of itself in these values: the Enable a tickbox with the pair's (i), the Call a choice of the free calls; undefined for a key that is no pair's. */
export function pairField(key: string, values: Readonly<Record<string, string>>): FieldInfo | undefined {
  const pair = pairFieldOf(key);
  if (pair === null) return undefined;
  if (pair.field === "ssid") return { label: t("settings.pair.call"), kind: "choice", choices: callChoices(key, values) };
  return {
    label: t("settings.enable.label"),
    name: t("settings.pair.name"),
    kind: "bool",
    tipLabel: t("settings.pair.tip_label"),
    tip: [t("settings.pair.tip1"), t("settings.pair.tip2")],
  };
}
