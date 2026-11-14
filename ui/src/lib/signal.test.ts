import { describe, expect, it } from "vitest";
import { readingText, signalLine, signalNumber } from "@/lib/signal";
import type { SignalSeriesMessage } from "@/protocol/protocol";
import { NOW, ago } from "@/test/fixtures";

const series = (points: SignalSeriesMessage["points"]): SignalSeriesMessage => ({ type: "signal_series", call: "OH2HF", hours: 24, points });
const DAY = 24 * 3600;

describe("signal: the readings in words", () => {
  it("writes the SNR in whole dB with a true minus sign, and the RSSI in dBm after it", () => {
    expect(readingText({ snr: -3, rssi: null })).toBe("SNR \u22123 dB");
    expect(readingText({ snr: -2.6, rssi: null })).toBe("SNR \u22123 dB");
    expect(readingText({ snr: 12, rssi: null })).toBe("SNR 12 dB");
    expect(readingText({ snr: 5, rssi: -97 })).toBe("SNR 5 dB, RSSI \u221297 dBm");
    expect(readingText({ snr: null, rssi: -97 })).toBe("RSSI \u221297 dBm");
  });

  it("says nothing for a packet whose radio gave no reading", () => {
    expect(readingText({ snr: null, rssi: null })).toBeNull();
  });

  it("writes a reading on the graph as in the text: half up, a true minus, no minus on 0", () => {
    expect(signalNumber(-2.5, 0)).toBe("\u22122");
    expect(signalNumber(-0.4, 0)).toBe("0");
    expect(signalNumber(-0.4, 1)).toBe("\u22120.4");
    expect(signalNumber(-0.04, 1)).toBe("0.0");
    expect(signalNumber(6, 0)).toBe("6");
    for (const value of [-3.5, -2.5, -0.4, 0, 4.5, 12]) expect(`SNR ${signalNumber(value, 0)} dB`).toBe(readingText({ snr: value, rssi: null }));
  });
});

describe("signal: the line of a station's signal", () => {
  const from = NOW - DAY * 1000;

  it("is none until the answer comes", () => {
    expect(signalLine(null, from)).toBeNull();
  });

  it("is the SNR of each packet that had one, oldest first, from the span's start", () => {
    const line = signalLine(
      series([
        [ago(DAY + 60), -9, null],
        [ago(3600), -5, null],
        [ago(60), 2, null],
      ]),
      from,
    );
    expect(line?.kind).toBe("snr");
    expect(line?.points.map((p) => p.v)).toEqual([-5, 2]);
  });

  it("is the RSSI when two packets have it and fewer have an SNR", () => {
    const line = signalLine(
      series([
        [ago(3600), null, -100],
        [ago(60), 4, -90],
      ]),
      from,
    );
    expect(line?.kind).toBe("rssi");
    expect(line?.points.map((p) => p.v)).toEqual([-100, -90]);
  });

  it("is none for a station with fewer than two readings", () => {
    expect(signalLine(series([]), from)).toBeNull();
    expect(signalLine(series([[ago(60), -3, null]]), from)).toBeNull();
    expect(signalLine(series([[ago(60), -3, null]]), from)).toBeNull();
  });
});
