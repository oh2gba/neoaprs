// What the card of a satellite says (components/SatelliteCard.vue): the next pass's rise (and how
// soon), how long it lasts, its set and its highest point; while it is up the time left, the
// elevation and the Doppler now. Then the frequencies, the mode and the altitude; the path is the
// card's copyable field, and with a pass a small table gives where to tune at rise, highest point
// and set. Only what the daemon sent: a frequency, mode or path the list is not sure of never
// comes. Times in the viewer's own time, the altitude by the page's unit switch.
import { dayText, formatNumber, t } from "@/i18n";
import { hourMinuteText, untilText } from "@/lib/format";
import { rangeText } from "@/lib/units";
import type { SatelliteCard, SatelliteLookNow, SatelliteTune } from "@/protocol/protocol";

export interface SatelliteRow {
  label: string;
  text: string;
}

const SECOND = 1000;
const MINUTE = 60 * SECOND;

/** The names of the modes, which no language translates. */
const MODE_NAMES: Readonly<Record<NonNullable<SatelliteCard["mode"]>, string>> = {
  afsk1200: "AFSK 1200",
  gmsk9600: "GMSK 9600",
};

/** A frequency in MHz to the kHz, in the language's figures. */
const mhzText = (hz: number): string => `${formatNumber(hz / 1e6, 3)} MHz`;

const degreesText = (deg: number): string => `${formatNumber(Math.round(deg), 0)}°`;

const sameDay = (a: Date, b: Date): boolean => a.toDateString() === b.toDateString();

/** A time of the pass: the hour and minute, with the day when it is not today. */
function whenText(iso: string, nowMs: number): string {
  const time = hourMinuteText(iso);
  const date = new Date(iso);
  return sameDay(date, new Date(nowMs)) ? time : t("layers.sat.day_time", { day: dayText(date, false), time });
}

/** A length of time: seconds under a minute, else whole minutes rounded up. */
function spanText(ms: number): string {
  return ms < MINUTE
    ? t("time.span.s", { n: Math.max(0, Math.ceil(ms / SECOND)) })
    : t("time.span.min", { n: Math.ceil(ms / MINUTE) });
}

/** The sample of now, between those the daemon sent; null when none covers it. */
export function lookAt(looks: readonly SatelliteLookNow[], nowMs: number): SatelliteLookNow | null {
  for (let i = 1; i < looks.length; i++) {
    const a = looks[i - 1];
    const b = looks[i];
    const ta = Date.parse(a.at);
    const tb = Date.parse(b.at);
    if (nowMs >= ta && nowMs <= tb) {
      const f = tb > ta ? (nowMs - ta) / (tb - ta) : 0;
      const mix = (x: readonly number[], y: readonly number[]) => x.map((v, j) => v + f * ((y[j] ?? v) - v));
      return {
        at: a.at,
        el_deg: a.el_deg + f * (b.el_deg - a.el_deg),
        down_hz: mix(a.down_hz, b.down_hz),
        up_hz: mix(a.up_hz, b.up_hz),
      };
    }
  }
  return null;
}

/** Whether the satellite is above the horizon now, in the pass the card has. */
export function isUp(card: SatelliteCard, nowMs: number): boolean {
  const seen = card.next_pass;
  return seen !== null && Date.parse(seen.rise) <= nowMs && nowMs < Date.parse(seen.set);
}

/** A shift in kHz with its sign: "+8.4 kHz". */
export const shiftText = (hz: number): string =>
  `${hz > 0 ? "+" : hz < 0 ? "−" : ""}${formatNumber(Math.abs(hz) / 1000, 1)} kHz`;

/** Where a value does not apply. */
const DASH = "–";

/** Whether the card's pass is over: shown as none until a new one comes. */
const isOver = (card: SatelliteCard, nowMs: number): boolean =>
  card.next_pass !== null && nowMs >= Date.parse(card.next_pass.set);

/** The labels of a card's downlinks, Doppler rows and uplinks: numbered where there are several. */
function linkLabels(card: SatelliteCard) {
  const several = card.downlinks.length > 1;
  return {
    down: (i: number): string => (several ? t("layers.sat.downlink_n", { n: i + 1 }) : t("layers.sat.downlink")),
    doppler: (i: number): string => (several ? t("layers.sat.doppler_n", { n: i + 1 }) : t("layers.sat.doppler")),
    up: (i: number): string =>
      card.uplinks.length > 1 ? t("layers.sat.uplink_n", { n: i + 1 }) : t("layers.sat.uplink"),
  };
}

/**
 * The pass's rows, the same before, during and after it so that nothing moves: rise, duration,
 * set, highest point, time left, elevation and a Doppler row for each downlink, a dash where a
 * value does not apply; all dashes once the pass is over.
 */
function passRows(card: SatelliteCard, nowMs: number): SatelliteRow[] {
  const seen = card.next_pass;
  if (seen === null) return [];
  const over = isOver(card, nowMs);
  const up = isUp(card, nowMs);
  const now = up ? lookAt(card.looks, nowMs) : null;
  const ahead = (text: string): string => (over ? DASH : text);
  const labels = linkLabels(card);
  return [
    {
      label: t("layers.sat.rise"),
      text: ahead(
        up
          ? whenText(seen.rise, nowMs)
          : t("layers.sat.when", { time: whenText(seen.rise, nowMs), until: untilText(seen.rise, nowMs) }),
      ),
    },
    { label: t("layers.sat.duration"), text: ahead(spanText(Date.parse(seen.set) - Date.parse(seen.rise))) },
    { label: t("layers.sat.set"), text: ahead(whenText(seen.set, nowMs)) },
    { label: t("layers.sat.highest"), text: ahead(degreesText(seen.max_el_deg)) },
    { label: t("layers.sat.left"), text: up ? spanText(Date.parse(seen.set) - nowMs) : DASH },
    { label: t("layers.sat.elevation"), text: now === null ? DASH : degreesText(Math.max(0, now.el_deg)) },
    ...card.downlinks.map((_, i) => ({
      label: labels.doppler(i),
      text: now?.down_hz[i] === undefined ? DASH : shiftText(now.down_hz[i]),
    })),
  ];
}

/** The card's rows, the path aside (the card's copyable field). */
export function satelliteRows(card: SatelliteCard, nowMs: number): SatelliteRow[] {
  return [
    ...passRows(card, nowMs),
    ...card.downlinks.map((one, i) => ({ label: linkLabels(card).down(i), text: mhzText(one.hz) })),
    ...card.uplinks.map((one, i) => ({ label: linkLabels(card).up(i), text: mhzText(one.hz) })),
    ...(card.mode === null ? [] : [{ label: t("layers.sat.mode"), text: MODE_NAMES[card.mode] }]),
    { label: t("station.field.altitude"), text: rangeText(card.alt_km) },
  ];
}

/**
 * Every label the card may have: it keeps the room of the widest, so the values stand still as
 * the pass begins and ends.
 */
export const satelliteLabels = (): string[] =>
  (
    [
      "layers.sat.rise",
      "layers.sat.duration",
      "layers.sat.set",
      "layers.sat.highest",
      "layers.sat.left",
      "layers.sat.elevation",
      "layers.sat.doppler",
      "layers.sat.downlink",
      "layers.sat.uplink",
      "layers.sat.mode",
      "station.field.altitude",
      "station.field.path",
    ] as const
  )
    .map((id) => t(id))
    .concat(
      (["layers.sat.downlink_n", "layers.sat.doppler_n", "layers.sat.uplink_n"] as const).map((id) => t(id, { n: 2 })),
    );

export interface TuneRow {
  label: string;
  /** at rise, highest point and set, in MHz */
  cells: [string, string, string];
}

/**
 * The table of where to tune at the next pass, a downlink to hear and an uplink to send on; none
 * without a pass, and dashes for a pass that is over.
 */
export function tuneRows(card: SatelliteCard, nowMs: number): TuneRow[] {
  if (card.next_pass === null) return [];
  const over = isOver(card, nowMs);
  const labels = linkLabels(card);
  const row = (label: string, one: SatelliteTune): TuneRow => ({
    label,
    cells: [one.rise_hz, one.max_hz, one.set_hz].map((hz) =>
      hz === null || over ? DASH : formatNumber(hz / 1e6, 3),
    ) as [string, string, string],
  });
  return [
    ...card.downlinks.map((one, i) => row(labels.down(i), one)),
    ...card.uplinks.map((one, i) => row(labels.up(i), one)),
  ];
}
