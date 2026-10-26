import { describe, expect, it } from "vitest";
import { answeredSince, askWait, kmOf, kmWrong, qruLook, receivedFrom, requestText, sentLine } from "@/lib/qru";
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
  it("is the daemon's rule: the same request a minute apart, any two ten seconds apart, rounded up to whole seconds", () => {
    expect([LIMITS.qru.askEverySec, LIMITS.qru.askGapSec]).toEqual([60, 10]);
    expect(askWait(null, NOW, "INFO")).toBe(0);
    expect(askWait({ text: "INFO", at: ago(0) }, NOW, "INFO")).toBe(60);
    expect(askWait({ text: "INFO", at: ago(20.4) }, NOW, "INFO")).toBe(40);
    expect(askWait({ text: "INFO", at: ago(60) }, NOW, "INFO")).toBe(0);
    expect(askWait({ text: "INFO", at: ago(0) }, NOW, "RP70")).toBe(10); // (a group right after the list: only the gap)
    expect(askWait({ text: "INFO", at: ago(9.5) }, NOW, "RP70")).toBe(1);
    expect(askWait({ text: "INFO", at: ago(10) }, NOW, "RP70")).toBe(0);
    expect(askWait({ text: "INFO", at: ago(3) }, NOW)).toBe(7);
  });

  it("counts the servers that answered since the request, not those of an earlier one", () => {
    const server = qruState().servers[0];
    expect(answeredSince({ text: "INFO", at: ago(20) }, [server, { ...server, call: "W1AW", at: ago(30) }])).toBe(1);
    expect(answeredSince({ text: "INFO", at: ago(10) }, [server])).toBe(0);
  });
});

describe("what the row of the section says", () => {
  const server = qruState().servers[0];
  it("is nothing before a request, a refusal over everything, then waiting, then the count or no answer", () => {
    expect(qruLook(null, [], "", NOW)).toBeNull();
    expect(qruLook({ text: "INFO", at: ago(5) }, [], "RX only: nothing is sent", NOW)).toMatchObject({
      state: "Not sent",
      tone: "tnc-waiting",
      line: "RX only: nothing is sent",
    });
    expect(qruLook({ text: "INFO", at: ago(5) }, [], "", NOW)?.line).toMatch(/^\d\d:\d\d · waiting for answers…$/);
    const answered = qruLook({ text: "INFO", at: ago(70) }, [server], "", NOW);
    expect([answered?.tone, answered?.line]).toEqual(["tnc-connected", expect.stringMatching(/ · 1 server answered$/) as string]);
    const silent = qruLook({ text: "INFO", at: ago(70) }, [], "", NOW);
    expect([silent?.tone, silent?.line]).toEqual(["tnc-stopped", expect.stringMatching(/ · no answer$/) as string]);
  });
});

describe("what a server's row says of the objects", () => {
  const server = (over: Partial<ReturnType<typeof qruState>["servers"][number]>) => ({ ...qruState().servers[0], ...over });

  it("names the objects that arrived by the server that sent them", () => {
    const found = receivedFrom([server({ call: "OH2DPN", received: ["A", "B"] }), server({ call: "W1AW", received: ["C"] })]);
    expect([...found]).toEqual([
      ["A", "OH2DPN"],
      ["B", "OH2DPN"],
      ["C", "W1AW"],
    ]);
  });

  it("counts them against the closing line, warns only for fewer once the time for late ones is over, and offers the request to ask again then", () => {
    expect(sentLine(server({ received: ["A", "B", "C", "D", "E"] }), NOW)).toEqual({ text: "sent 5 · 5 arrived", warn: false, again: null });
    expect(sentLine(server({ sent_objects: 1, received: [], settles_at: ago(1), request: "TEST 150" }), NOW)).toEqual({
      text: "sent 1 · 0 arrived",
      warn: true,
      again: "TEST 150",
    });
    expect(sentLine(server({ sent_objects: 1, received: [], settles_at: ago(-5), request: "TEST 150" }), NOW)).toEqual({
      text: "sent 1 · 0 arrived",
      warn: false,
      again: null,
    });
    expect(sentLine(server({ sent_objects: 1, received: [], settles_at: ago(1), request: "" }), NOW)?.again).toBeNull();
  });

  it("is none before a closing line when nothing arrived, and counts what arrived when there was none", () => {
    const bare = { sent_objects: null, request: "", settles_at: null, sent: "", sent_at: null, received: [] as string[] };
    expect(sentLine(server(bare), NOW)).toBeNull();
    expect(sentLine(server({ ...bare, received: ["A"] }), NOW)).toEqual({ text: "1 arrived", warn: false, again: null });
  });
});
