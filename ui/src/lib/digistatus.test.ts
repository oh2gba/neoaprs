import { describe, expect, it } from "vitest";
import { digiLook, pairLook, type PairLink } from "@/lib/digistatus";
import type { PassStats } from "@/protocol/protocol";
import { ago, lineStats, NOW } from "@/test/fixtures";

/** What the pair passed onto a radio from radio `heard_on`. */
const passed = (heard_on: number, extra: Partial<PassStats> = {}): PassStats => ({
  heard_on,
  sent: 0,
  sent_at: null,
  held: 0,
  too_long: 0,
  ...extra,
});

/** The pair of radio 1 (FM) and radio 2 (Mercury), with what was passed onto each. */
const pair = (ontoFirst: PassStats[] = [], ontoSecond: PassStats[] = []): PairLink => ({
  first: { id: 1, name: "FM radio", stats: lineStats({ passed: ontoFirst }) },
  second: { id: 2, name: "Mercury radio", stats: lineStats({ passed: ontoSecond }) },
});

describe("pairLook", () => {
  it("says on and none passed yet while nothing went either way, with nothing behind the arrow but since when it counts", () => {
    expect(pairLook(pair(), null, NOW, false)).toEqual({
      state: "on",
      tone: "tnc-connected",
      line: "None repeated yet",
      since: "",
      ways: "",
      held: [],
      tooLong: [],
    });
    expect(pairLook(pair(), ago(3600), NOW, false).since).toMatch(/^Counted since /);
  });

  it("counts both ways together with the age of the later frame, and says each way behind the arrow", () => {
    const look = pairLook(
      pair([passed(2, { sent: 1, sent_at: ago(600) })], [passed(1, { sent: 3, sent_at: ago(120) })]),
      null,
      NOW,
      false,
    );
    expect(look.line).toBe("4 packets repeated · last 2 min ago");
    expect(look.ways).toBe("1 to FM radio · 3 to Mercury radio");
    expect(pairLook(pair([], [passed(1, { sent: 1, sent_at: ago(60) })]), null, NOW, false).ways).toBe(
      "0 to FM radio · 1 to Mercury radio",
    );
  });

  it("reads only what came from the other radio of the pair", () => {
    const look = pairLook(pair([passed(3, { sent: 5, sent_at: ago(60), held: 2 })]), null, NOW, false);
    expect([look.line, look.ways, look.held]).toEqual(["None repeated yet", "", []]);
  });

  it("says what was held back and what was too long by the radio it was for, each only when there is some", () => {
    const look = pairLook(pair([passed(2, { held: 1 })], [passed(1, { held: 3, too_long: 2 })]), null, NOW, false);
    expect(look.held).toEqual([
      "1 frame held back: too many for FM radio",
      "3 frames held back: too many for Mercury radio",
    ]);
    expect(look.tooLong).toEqual(["2 frames too long for Mercury radio"]);
    expect(look.line).toBe("None repeated yet");
  });

  it("says off in the warn colour while RX only is on, and keeps what is behind the arrow", () => {
    const look = pairLook(pair([], [passed(1, { sent: 2, sent_at: ago(60), held: 1 })]), null, NOW, true);
    expect([look.state, look.tone, look.line]).toEqual(["off", "tnc-waiting", "RX only: nothing is repeated"]);
    expect([look.ways, look.held]).toEqual([
      "0 to FM radio · 2 to Mercury radio",
      ["1 frame held back: too many for Mercury radio"],
    ]);
  });
});

describe("digiLook", () => {
  it("says a radio's own digipeater as before: the count and the age, the burst's held behind the arrow, off while RX only", () => {
    const tnc = { stats: lineStats({ digipeated: 12, digipeated_at: ago(180), digipeat_held: 2 }) };
    expect(digiLook(tnc, null, NOW, false)).toEqual({
      state: "on",
      tone: "tnc-connected",
      line: "12 packets repeated · last 3 min ago",
      since: "",
      held: "2 frames held back: too many in a burst",
    });
    expect(digiLook({ stats: lineStats() }, null, NOW, false).line).toBe("None repeated yet");
    expect(digiLook(tnc, null, NOW, true).line).toBe("RX only: nothing is repeated");
  });
});
