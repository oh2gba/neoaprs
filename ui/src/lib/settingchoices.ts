// The choices of the settings that offer a few (the status's and the beacon's interval, the antenna's direction, where the position comes from, how a moving station travels), as the words of the page's language, made when they are read.
import { t } from "@/i18n";
import { STATION_HOURS } from "@/lib/aging";

export interface Choice {
  value: string;
  label: string;
}

/** What On stores for a moving station that was Off: the interval a fixed station is offered first (the daemon does not use it there). */
export const MOVING_BEACON_ON = "30";

export const every = (minutes: number | string): string => t("settings.every_min", { minutes });

/** The status's choices: every 30 or 60 minutes or every 2 hours (15 is the least the daemon takes). */
export const statusIntervalChoices = (): readonly Choice[] => [
  { value: "30", label: every(30) },
  { value: "60", label: every(60) },
  { value: "120", label: t("settings.every_hours", { n: 2 }) },
];

/** The beacon's choices: off, or every 30 or 60 minutes or every 3 hours (20 is the least the daemon takes; a stored 20 shows as one more choice). */
export const beaconChoices = (): readonly Choice[] => [
  { value: "0", label: t("settings.beacon_interval.off") },
  { value: "30", label: every(30) },
  { value: "60", label: every(60) },
  { value: "180", label: t("settings.every_hours", { n: 3 }) },
];

/** How long a station stays on the map: 1 h, 3 h, 6 h, 12 h or 24 h (the Stations tab offers them). */
export const stationHoursChoices = (): readonly Choice[] =>
  STATION_HOURS.map((hours) => ({ value: String(hours), label: t("station.table.hours", { n: hours }) }));

/** The beacon of a station that moves (a GPS is chosen): Off, or On, which SmartBeaconing times. On stores the interval a fixed station is offered first; a moving station does not use it. */
export const movingBeaconChoices = (): readonly Choice[] => [
  { value: "0", label: t("settings.beacon_interval.off") },
  { value: MOVING_BEACON_ON, label: t("settings.beacon_interval.on_smart") },
];

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
export const directionChoices = (): readonly Choice[] => [
  { value: "omni", label: t("settings.antenna_direction.omni") },
  ...COMPASS.map((point) => ({ value: point, label: point })),
];

/** Where the position of the beacon comes from (gps/source): Fixed (a station at its stored location), a GPS read through gpsd, or a GPS on a serial port (a moving station). */
export const positionChoices = (): readonly Choice[] => [
  { value: "off", label: t("settings.position.fixed") },
  { value: "gpsd", label: t("settings.position.gpsd") },
  { value: "serial", label: t("settings.position.serial") },
];

/** How a moving station travels (beacon/travel), the way SmartBeaconing is set for it; the car is the daemon's default. */
export const travelChoices = (): readonly Choice[] => [
  { value: "car", label: t("settings.travel.car") },
  { value: "bicycle", label: t("settings.travel.bicycle") },
  { value: "foot", label: t("settings.travel.foot") },
  { value: "boat", label: t("settings.travel.boat") },
];
