import { describe, expect, it } from "vitest";
import { reportLook, statusRadioLines } from "@/lib/statusreport";
import { NOW, ago } from "@/test/fixtures";

describe("reportLook", () => {
  it("says when the last report went and when the next is due, in the form of the beacon's line", () => {
    expect(reportLook(ago(240), "30", false, false, NOW)).toEqual({
      state: "on",
      tone: "beacon-on",
      line: "Last sent 4 min ago · next in 26 min (every 30 min)",
    });
  });

  it("says the next is due now once the interval has passed", () => {
    expect(reportLook(ago(31 * 60), "30", false, false, NOW).line).toBe("Last sent 31 min ago · next now (every 30 min)");
  });

  it("says not sent yet, and the text of the field is never the line", () => {
    expect(reportLook(null, "30", false, false, NOW).line).toBe("Not sent yet");
  });

  it("says there is no timed status while the beacon is Off or the interval is no number", () => {
    expect(reportLook(ago(240), "30", true, false, NOW).line).toBe("Last sent 4 min ago · no timed status");
    expect(reportLook(ago(240), "", false, false, NOW).line).toBe("Last sent 4 min ago · no timed status");
  });

  it("is off in the warn colour and says nothing is sent in RX only, whatever was sent before", () => {
    expect(reportLook(ago(240), "30", false, true, NOW)).toEqual({ state: "off", tone: "tnc-waiting", line: "RX only: nothing is sent" });
    expect(reportLook(null, "30", true, true, NOW).line).toBe("RX only: nothing is sent");
  });
});

describe("statusRadioLines", () => {
  const later = (minutes: number) => new Date(NOW + minutes * 60_000).toISOString();

  it("says the status on each radio by its name: the last and the next with that radio's interval, none yet, or no timed status", () => {
    expect(
      statusRadioLines(
        [
          { name: "FM", status: { last_sent: ago(240), next_due: later(11), interval_min: 15 } },
          { name: "HF", status: { last_sent: null, next_due: null, interval_min: 30 } },
          { name: "LoRa", status: { last_sent: ago(120), next_due: null, interval_min: 30 } },
        ],
        NOW,
      ),
    ).toEqual(["FM: last sent 4 min ago · next in 11 min (every 15 min)", "HF: not sent yet", "LoRa: last sent 2 min ago · no timed status"]);
    expect(statusRadioLines([], NOW)).toEqual([]);
  });
});
