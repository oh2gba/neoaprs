import { describe, expect, it } from "vitest";
import { answeredSince, askWait, kmOf, kmWrong, qruLook, requestText } from "@/lib/qru";
import { LIMITS } from "@/protocol/lists";
import { NOW, ago, qruState } from "@/test/fixtures";

describe("the distance of a request for local info", () => {
  it("is empty, or a whole number of km from 1 to the most the daemon takes", () => {
    expect(kmOf("")).toBeNull();
    expect(kmOf("  ")).toBeNull();
    expect(kmOf(" 150 ")).toBe(150);
    expect(kmOf("1")).toBe(1);
    expect(kmOf(String(LIMITS.qru.kmMax))).toBe(LIMITS.qru.kmMax);
    for (const wrong of ["0", String(LIMITS.qru.kmMax + 1), "-5", "1.5", "5 km", "x", "100000"]) expect(kmWrong(wrong), wrong).toBe(true);
    expect(kmWrong("")).toBe(false);
  });

  it("goes after the word in the text of the request, none for a wrong one", () => {
    expect(requestText("INFO", "")).toBe("INFO");
    expect(requestText("RP70", "20")).toBe("RP70 20");
    expect(requestText("RP70", "0")).toBeNull();
  });
});

describe("the minute between two requests", () => {
  it("is the daemon's number, counted from the request that was sent, rounded up to whole seconds, and none before a request or after the minute", () => {
    expect(LIMITS.qru.askEverySec).toBe(60);
    expect(askWait(null, NOW)).toBe(0);
    expect(askWait({ text: "INFO", at: ago(0) }, NOW)).toBe(60);
    expect(askWait({ text: "INFO", at: ago(20.4) }, NOW)).toBe(40);
    expect(askWait({ text: "INFO", at: ago(59) }, NOW)).toBe(1);
    expect(askWait({ text: "INFO", at: ago(60) }, NOW)).toBe(0);
    expect(askWait({ text: "INFO", at: ago(600) }, NOW)).toBe(0);
  });

  it("counts the servers that answered since the request, not those of an earlier one", () => {
    const [server] = qruState().servers;
    expect(answeredSince({ text: "INFO", at: ago(20) }, [server!, { ...server!, call: "W1AW", at: ago(30) }])).toBe(1);
    expect(answeredSince({ text: "INFO", at: ago(10) }, [server!])).toBe(0);
  });
});

describe("what the row of the section says", () => {
  const [server] = qruState().servers;
  it("is nothing before a request, a refusal over everything, then waiting, then the count or no answer", () => {
    expect(qruLook(null, [], "", NOW)).toBeNull();
    expect(qruLook({ text: "INFO", at: ago(5) }, [], "RX only: nothing is sent", NOW)).toMatchObject({ state: "Not sent", tone: "tnc-waiting", line: "RX only: nothing is sent" });
    expect(qruLook({ text: "INFO", at: ago(5) }, [], "", NOW)?.line).toMatch(/^\d\d:\d\d · waiting for answers…$/);
    expect(qruLook({ text: "INFO", at: ago(70) }, [server!], "", NOW)).toMatchObject({ tone: "tnc-connected", line: expect.stringMatching(/ · 1 server answered$/) });
    expect(qruLook({ text: "INFO", at: ago(70) }, [], "", NOW)).toMatchObject({ tone: "tnc-stopped", line: expect.stringMatching(/ · no answer$/) });
  });
});
