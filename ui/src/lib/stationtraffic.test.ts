// The traffic of one station (lib/stationtraffic.ts): which packets are its, the two places they come from made one list, the answer each directed query asks for, and the state of a query of ours. And the operator's own
// query held to the daemon's rule (lib/query.ts).
import { describe, expect, it } from "vitest";
import { customQuery } from "@/lib/query";
import { ANSWER_WAIT_MS, answers, isTrafficOf, mergeTraffic, nextDeadline, queryAsked, queryState, TRAFFIC_SHOWN } from "@/lib/stationtraffic";
import { NOW, packet, packetAt as at, sentMessage as msg } from "@/test/fixtures";
import type { PacketRow } from "@/protocol/protocol";

const position = (id: number, seconds: number, extra: Partial<PacketRow> = {}) =>
  packet(id, { heard_at: at(seconds), tnc2: `OH2RDG>APRS:!${seconds}`, ...extra });
const status = (id: number, seconds: number) =>
  packet(id, {
    heard_at: at(seconds),
    kind: "status",
    tnc2: `OH2RDG>APRS:>${id}`,
    decoded: { type: "status", text: "on", locator: null, frequency: null, timestamp: null },
  });

describe("the traffic of a station", () => {
  it("is what it sent (inside a third-party packet too) and the messages we sent to it, not what it was sent by others or what we sent to others", () => {
    expect(isTrafficOf(position(1, 0), "OH2RDG")).toBe(true);
    expect(isTrafficOf(position(2, 0, { source: "OH7JHF-1", sender: "OH2RDG", via: "rf-gated", gate: "OH7JHF-1" }), "OH2RDG")).toBe(true);
    expect(isTrafficOf(msg(3, "OH2GBA", "OH2RDG", "?APRSP", 0), "OH2RDG")).toBe(true);
    expect(isTrafficOf(msg(4, "OH2GBA", "OH2XYZ", "hello", 0), "OH2RDG")).toBe(false);
    expect(isTrafficOf(msg(5, "OH2XYZ", "OH2RDG", "hello", 0), "OH2RDG")).toBe(false);
  });

  it("is one list of the log's answer and what came after, each packet once, the newest first, at most the latest 50", () => {
    const logged = [position(900, -10), position(901, -20)];
    const live = [position(5, -10), position(6, 5)]; // (the first is the log's first: the same time, direction and line, another id)
    expect(mergeTraffic(live, logged, true).map((r) => r.heard_at)).toEqual([at(5), at(-10), at(-20)]);
    const many = Array.from({ length: TRAFFIC_SHOWN + 5 }, (_, i) => position(i + 1, i));
    const merged = mergeTraffic(many, [], true);
    expect(merged).toHaveLength(TRAFFIC_SHOWN);
    expect(merged[0]?.heard_at).toBe(at(TRAFFIC_SHOWN + 4));
  });

  it("leaves out the packets from the internet while Internet stations is off", () => {
    const rows = [position(1, 0, { via: "is", tnc2: "OH2RDG>APRS,TCPIP*:!x" }), position(2, 1)];
    expect(mergeTraffic(rows, [], true)).toHaveLength(2);
    expect(mergeTraffic(rows, [], false).map((r) => r.id)).toEqual([2]);
  });
});

describe("a directed query of ours in the traffic", () => {
  it("is a message of ours to the station with no id whose text begins with ?", () => {
    expect(queryAsked(msg(1, "OH2GBA", "OH2RDG", "?aprsp", 0), "OH2RDG")).toBe("?APRSP");
    expect(
      queryAsked(
        msg(1, "OH2GBA", "OH2RDG", "?APRSP", 0, {
          decoded: { type: "message", addressee: "OH2RDG", text: "?APRSP", msg_id: "01", ack_id: null, rej_id: null },
        }),
        "OH2RDG",
      ),
    ).toBeNull();
    expect(queryAsked(msg(1, "OH2GBA", "OH2RDG", "hello", 0), "OH2RDG")).toBeNull();
    expect(queryAsked(msg(1, "OH2XYZ", "OH2RDG", "?APRSP", 0), "OH2RDG")).toBeNull();
  });

  it.each([
    ["?APRSP", position(2, 5), true],
    ["?APRSP", status(2, 5), false],
    ["?APRSS", status(2, 5), true],
    ["?APRSD", msg(2, "OH2RDG", "OH2GBA", "Directs= OH2XYZ OH2ABC", 5), true],
    ["?APRSD", msg(2, "OH2RDG", "OH2GBA", "hello", 5), false],
    ["?APRST", msg(2, "OH2RDG", "OH2GBA", "OH2GBA>WIDE1-1>OH2RDG", 5), true],
    ["?PING?", msg(2, "OH2RDG", "OH2GBA", "PONG", 5), true],
    [
      "?APRST",
      msg(2, "OH2RDG", "OH2GBA", "", 5, { decoded: { type: "message", addressee: "OH2GBA", text: "", msg_id: null, ack_id: "01", rej_id: null } }),
      false,
    ],
    ["?WX?", position(2, 5, { decoded: { ...position(2, 5).decoded, weather: { temp_c: 5 } } as PacketRow["decoded"] }), true],
    ["?WX?", position(2, 5), false],
    ["?APRSO", status(2, 5), true],
  ])("%s is answered by this packet: %s", (query, reply, expected) => {
    expect(answers(query, reply)).toBe(expected);
  });

  it("is waiting, then answered when the answer comes from the station after it, or no answer after two minutes", () => {
    const asked = msg(1, "OH2GBA", "OH2RDG", "?APRSP", 0);
    const earlier = position(2, -5);
    expect(queryState(asked, "OH2RDG", [asked, earlier], NOW + 1000)).toBe("waiting");
    expect(queryState(asked, "OH2RDG", [asked, earlier], NOW + ANSWER_WAIT_MS)).toBe("no_answer");
    expect(nextDeadline("OH2RDG", [asked, earlier], NOW + 1000)).toBe(NOW + ANSWER_WAIT_MS);
    const answer = position(3, 30);
    expect(queryState(asked, "OH2RDG", [answer, asked], NOW + 1000)).toBe("answered");
    expect(queryState(asked, "OH2RDG", [answer, asked], NOW + 10 * ANSWER_WAIT_MS)).toBe("answered");
    expect(nextDeadline("OH2RDG", [answer, asked], NOW + 1000)).toBeNull();
    expect(queryState(earlier, "OH2RDG", [answer, asked], NOW)).toBeNull();
  });
});

describe("the operator's own query", () => {
  it.each([["APRSH OH2GBA-15"], ["?"], ["   ?   "], ["?" + "A".repeat(67)], ["?APRS{1"], ["?APRS|"], ["?APRS~"], ["?APRSÄ"], ["?APRS\tX"]])(
    "refuses %j",
    (text) => {
      expect("problem" in customQuery(text)).toBe(true);
    },
  );

  it("says what is wrong: no query, too long, a character a query cannot carry", () => {
    expect(customQuery("APRSH")).toEqual({ problem: "form" });
    expect(customQuery("?" + "A".repeat(67))).toEqual({ problem: "long" });
    expect(customQuery("?APRS{1")).toEqual({ problem: "chars" });
  });

  it("takes ?APRSH OH2GBA-15, and sends a query trimmed and upper-cased", () => {
    expect(customQuery("?APRSH OH2GBA-15")).toEqual({ text: "?APRSH OH2GBA-15" });
    expect(customQuery("  ?aprsh oh2gba-15 ")).toEqual({ text: "?APRSH OH2GBA-15" });
    expect(customQuery("?" + "A".repeat(66))).toEqual({ text: "?" + "A".repeat(66) });
  });
});
