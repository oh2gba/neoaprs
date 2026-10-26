import { describe, expect, it } from "vitest";
import { reportLook } from "@/lib/statusreport";
import { NOW, ago } from "@/test/fixtures";

describe("reportLook", () => {
  it("says when the last report went and when the next may, if what it says has changed", () => {
    expect(reportLook(ago(240), "30", false, false, NOW)).toEqual({ state: "on", tone: "beacon-on", line: "Last sent 4 min ago · next in 26 min if changed" });
  });

  it("says the next goes as soon as it changes once the interval has passed", () => {
    expect(reportLook(ago(31 * 60), "30", false, false, NOW).line).toBe("Last sent 31 min ago · next as soon as it changes");
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
