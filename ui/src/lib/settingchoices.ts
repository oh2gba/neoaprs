// Choices for the settings that offer a few (status and beacon interval, antenna direction,
// position source, how a moving station travels), as words in the page's language made when read.
import { t } from "@/i18n";
import { STATION_HOURS } from "@/lib/aging";

export interface Choice {
  value: string;
  label: string;
  /** Hover text for the option, where the label does not say it all (a sound card's id). */
  title?: string;
  /** Offered greyed: a device another radio holds (lib/portchoice.ts). */
  disabled?: boolean;
  /**
   * The heading of the group the option stands under (Add radio's Packet, Mercury, LoRa, Without a radio); a
   * group's options are adjacent.
   */
  group?: string;
}

/**
 * What On stores for a moving station that was Off: the interval a fixed station is offered first
 * (unused there).
 */
export const MOVING_BEACON_ON = "30";

export const every = (minutes: number | string): string => t("settings.every_min", { minutes });

/** The status choices: every 30 or 60 minutes or every 2 hours (15 is the daemon's least). */
export const statusIntervalChoices = (): readonly Choice[] => [
  { value: "30", label: every(30) },
  { value: "60", label: every(60) },
  { value: "120", label: t("settings.every_hours", { n: 2 }) },
];

/**
 * The beacon choices: off, or every 30 or 60 minutes or every 3 hours (20 is the daemon's least; a
 * stored 20 shows too).
 */
export const beaconChoices = (): readonly Choice[] => [
  { value: "0", label: t("settings.beacon_interval.off") },
  { value: "30", label: every(30) },
  { value: "60", label: every(60) },
  { value: "180", label: t("settings.every_hours", { n: 3 }) },
];

/** How long a station stays on the map: 1, 3, 6, 12 or 24 h (offered in the Stations tab). */
export const stationHoursChoices = (): readonly Choice[] =>
  STATION_HOURS.map((hours) => ({ value: String(hours), label: t("station.table.hours", { n: hours }) }));

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
export const directionChoices = (): readonly Choice[] => [
  { value: "omni", label: t("settings.antenna_direction.omni") },
  ...COMPASS.map((point) => ({ value: point, label: point })),
];

/**
 * Where the beacon position comes from (gps/source): Fixed (the stored location), a GPS through
 * gpsd, or a serial GPS.
 */
export const positionChoices = (): readonly Choice[] => [
  { value: "off", label: t("settings.position.fixed") },
  { value: "gpsd", label: t("settings.position.gpsd") },
  { value: "serial", label: t("settings.position.serial") },
];

/**
 * How a moving station travels (beacon/travel), which sets its SmartBeaconing; the car is the
 * daemon's default.
 */
export const travelChoices = (): readonly Choice[] => [
  { value: "car", label: t("settings.travel.car") },
  { value: "bicycle", label: t("settings.travel.bicycle") },
  { value: "foot", label: t("settings.travel.foot") },
  { value: "boat", label: t("settings.travel.boat") },
];

/**
 * What each SSID is for, per aprs.org (SSIDs.txt), in a few words that begin with the number as
 * written after the call.
 */
const SSID_LABELS = [
  "settings.ssid.s0",
  "settings.ssid.s1",
  "settings.ssid.s2",
  "settings.ssid.s3",
  "settings.ssid.s4",
  "settings.ssid.s5",
  "settings.ssid.s6",
  "settings.ssid.s7",
  "settings.ssid.s8",
  "settings.ssid.s9",
  "settings.ssid.s10",
  "settings.ssid.s11",
  "settings.ssid.s12",
  "settings.ssid.s13",
  "settings.ssid.s14",
  "settings.ssid.s15",
] as const;

/** The call's SSID dropdown: none first (empty text), then 1 to 15; the value is the number. */
export const ssidChoices = (): readonly Choice[] =>
  SSID_LABELS.map((id, n) => ({ value: n === 0 ? "" : String(n), label: t(id) }));
