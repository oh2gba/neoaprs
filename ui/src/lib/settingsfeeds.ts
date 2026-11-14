// The switches of the groups Ships (AIS) and Aircraft (ADS-B) of the Settings tab (lib/settings.ts): each is Enable, as the group's title names the feature, with its (i) that says what the map shows and that nothing is sent.
import type { FieldSpec } from "@/lib/settings";

const FEEDS = ["ais", "adsb"] as const;

/** The fields `ais/enabled` and `adsb/enabled`. */
export function feedSwitches(): Record<string, FieldSpec> {
  const spec = (feed: (typeof FEEDS)[number]): FieldSpec => ({
    name: `settings.${feed}.name`,
    label: "settings.enable.label",
    kind: "bool",
    tipLabel: `settings.${feed}.tip_label`,
    tip: [`settings.${feed}.tip1`, `settings.${feed}.tip2`],
  });
  return Object.fromEntries(FEEDS.map((feed) => [`${feed}/enabled`, spec(feed)]));
}
