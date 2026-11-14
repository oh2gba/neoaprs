// The signal of what was heard as the page writes it: the readings a radio measured of a frame (the SNR in dB, the RSSI in dBm, each there or not: neoaprs/reading.py) in one short text, and the line of a station's signal over time
// for its card (components/StationSignal.vue). Plain functions of the rows and of the daemon's answer (`signal_series`).
import { formatNumber, t } from "@/i18n";
import type { Point } from "@/lib/chart";
import { snrText } from "@/lib/waterfall";
import type { SignalSeriesMessage } from "@/protocol/protocol";

/** How far back the graph of a station's signal goes: a day, as the weather and packet graphs do. */
export const SIGNAL_HOURS = 24;
/** A graph needs two readings to be a line. */
const LEAST_POINTS = 2;

interface Readings {
  snr: number | null;
  rssi: number | null;
}

/** The readings of a frame in words, "SNR −3 dB" or "SNR −3 dB, RSSI −97 dBm" (whole numbers, a true minus sign); null when the radio gave none: nothing is said then. */
export function readingText(readings: Readings): string | null {
  const parts = [
    readings.snr === null ? null : t("packets.signal.snr", { value: snrText(readings.snr) }),
    readings.rssi === null ? null : t("packets.signal.rssi", { value: snrText(readings.rssi) }),
  ];
  const said = parts.filter((part) => part !== null);
  return said.length === 0 ? null : said.join(", ");
}

/** A reading as the graph writes it, in its readout and on its axis, the way the text writes it (`readingText`): rounded half up, with a true minus sign, and no minus on a value that rounds to 0. */
export function signalNumber(value: number, decimals: number): string {
  const scale = 10 ** decimals;
  const rounded = Math.round(value * scale) / scale;
  return `${rounded < 0 ? "\u2212" : ""}${formatNumber(Math.abs(rounded), decimals)}`;
}

/** What the graph shows: the SNR when two of the readings have one, else the RSSI when two have it, else nothing. */
export interface SignalLine {
  kind: "snr" | "rssi";
  points: Point[];
}

/** The line of the graph from the daemon's answer: null until the answer comes and for a station with fewer than two readings of either kind. */
export function signalLine(series: SignalSeriesMessage | null, from: number): SignalLine | null {
  if (series === null) return null;
  const since = series.points.filter(([at]) => Date.parse(at) >= from);
  for (const [kind, index] of [
    ["snr", 1],
    ["rssi", 2],
  ] as const) {
    const points = since.flatMap((point) => {
      const value = point[index];
      return value === null ? [] : [{ t: Date.parse(point[0]), v: value }];
    });
    if (points.length >= LEAST_POINTS) return { kind, points };
  }
  return null;
}
