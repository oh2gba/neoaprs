// The alerts the operator sets on stations ("Alert me when…" in the menu of a row of the Stations table): which stations can have one, what the bell of a row says, and the words of an alert that fired. The daemon keeps the alert
// (the topic `station_prefs`, its `alert`) and watches the stations, so it works with no page open; a page is told what fired by the message `station_alert` and says it in the language of the page.
import { t } from "@/i18n";
import { distanceText, hourMinuteText } from "@/lib/format";
import { LIMITS } from "@/protocol/lists";
import type { AlertWhen, StationAlertMessage, StationRow } from "@/protocol/protocol";

/** The distance the choice starts with for "comes within N km of me". */
export const ALERT_KM_DEFAULT = 10;
export const ALERT_KM_MIN = LIMITS.alert.kmMin;
export const ALERT_KM_MAX = LIMITS.alert.kmMax;

/** Whether a station can have an alert: a station heard (not an object or an item), not ourselves and not one of ours. */
export function canAlert(row: Pick<StationRow, "kind" | "is_me" | "own">): boolean {
  return row.kind === "station" && !row.is_me && !row.own;
}

/** What an alert watches, in short words for the bell's title: "on the air, within 10 km, heard direct". */
export function alertSummary(alert: AlertWhen): string {
  const parts = [
    alert.on_air ? t("station.alert.part.on_air") : null,
    alert.within_km !== null ? t("station.alert.part.within", { km: alert.within_km }) : null,
    alert.direct ? t("station.alert.part.direct") : null,
  ];
  return parts.filter((part) => part !== null).join(", ");
}

/** What happened, in the page's language: "OH2XYZ is on the air", "OH2XYZ is 8.2 km from you", "OH2XYZ is heard direct". */
export function firedText(message: Pick<StationAlertMessage, "call" | "kind" | "km">): string {
  if (message.kind === "within") return t("station.alert.fired.within", { call: message.call, km: distanceText(message.km) });
  return message.kind === "on_air" ? t("station.alert.fired.on_air", { call: message.call }) : t("station.alert.fired.direct", { call: message.call });
}

/** The words of the toast: what happened, with the time of the packet that fired it ("12:03 OH2XYZ is on the air"). */
export function firedLine(message: StationAlertMessage): string {
  return t("station.alert.fired.line", { time: hourMinuteText(message.at), text: firedText(message) });
}
