// The fields of the groups Ships (AIS) and Aircraft (ADS-B) of the Settings tab (lib/settings.ts): each group's switch is Enable, as the group's title names the feature, with its (i) that says what the map shows and
// that nothing is sent; then, for the ships, a tickbox for each colour group that is shown and whether the still ones are left out; and for both how far round us they are read (typed, 50 to 450 km) and how long a track each draws.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { Choice } from "@/lib/settingchoices";
import type { FieldSpec } from "@/lib/settings";

/** The choices the daemon takes (neoaprs/configtraffic.py; the ship types are its ais.CATEGORIES). */
const TRACK_MINUTES = [0, 15, 30, 60, 180, 720];
const SHIP_TYPES = ["cargo", "tanker", "passenger", "highspeed", "fishing", "pleasure", "special", "other"] as const;

const trackChoices = (): readonly Choice[] =>
  TRACK_MINUTES.map((minutes) => ({
    value: String(minutes),
    label: minutes === 0 ? t("settings.traffic.track.off") : minutes < 60 ? `${minutes} min` : `${minutes / 60} h`,
  }));
const typeChoices = (): readonly Choice[] => SHIP_TYPES.map((type) => ({ value: type, label: t(`settings.ais.types.${type}`) }));

/** The fields of the two groups by key. */
export function feedSwitches(): Record<string, FieldSpec> {
  const enable = (name: MessageId, tipLabel: MessageId, tip: MessageId[]): FieldSpec => ({ name, label: "settings.enable.label", kind: "bool", tipLabel, tip });
  const radius: FieldSpec = { label: "settings.traffic.radius.label", unit: "km", tip: ["settings.traffic.radius.tip1"] };
  const track: FieldSpec = { label: "settings.traffic.track.label", kind: "choice", choices: trackChoices, tip: ["settings.traffic.track.tip1"] };
  return {
    "ais/enabled": enable("settings.ais.name", "settings.ais.tip_label", ["settings.ais.tip1", "settings.ais.tip2"]),
    "adsb/enabled": enable("settings.adsb.name", "settings.adsb.tip_label", ["settings.adsb.tip1", "settings.adsb.tip2"]),
    "ais/types": { label: "settings.ais.types.label", kind: "multi", choices: typeChoices, tip: ["settings.ais.types.tip1"] },
    "ais/hide_still": { label: "settings.ais.hide_still.label", kind: "bool", tip: ["settings.ais.hide_still.tip1"] },
    "ais/radius_km": radius,
    "ais/track_min": track,
    "adsb/radius_km": radius,
    "adsb/track_min": track,
  };
}
