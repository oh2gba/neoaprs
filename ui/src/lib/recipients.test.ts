import { describe, expect, it } from "vitest";
import { addable, candidates, canSendAll, matching, recipientsOf } from "@/lib/recipients";
import { NOW, ago, station } from "@/test/fixtures";

const book = (...rows: ReturnType<typeof station>[]) => new Map(rows.map((r) => [r.call, r]));

describe("candidates", () => {
  it("lists the stations heard in the last day, those heard direct first, then the newest", () => {
    const list = candidates(
      book(
        station("OH2OLD", { last_heard: ago(100) }),
        station("OH2NEW", { last_heard: ago(10) }),
        station("OH2DIR", { last_heard: ago(500), heard_direct: 4 }),
        station("OH2GONE", { last_heard: ago(25 * 3600) }),
      ),
      "OH2GBA",
      NOW,
    );
    expect(list.map((c) => c.call)).toEqual(["OH2DIR", "OH2NEW", "OH2OLD"]);
    expect(list.map((c) => c.direct)).toEqual([true, false, false]);
  });

  it("leaves out objects, items, ourselves and the email gateway", () => {
    const list = candidates(
      book(
        station("LEADER", { kind: "object" }),
        station("KIOSK", { kind: "item" }),
        station("OH2GBA", { is_me: true }),
        station("OH2GBA-7"),
        station("EMAIL-2"),
        station("OH2RDG"),
      ),
      "oh2gba-7",
      NOW,
    );
    expect(list.map((c) => c.call)).toEqual(["OH2RDG"]);
  });
});

describe("matching", () => {
  const list = candidates(book(station("OH2RDG"), station("OH2PU-9"), station("OH3XYZ")), null, NOW);

  it("keeps the calls that contain the filter, in capitals or not, and all of them for an empty one", () => {
    expect(
      matching(list, "oh2")
        .map((c) => c.call)
        .sort(),
    ).toEqual(["OH2PU-9", "OH2RDG"]);
    expect(matching(list, " xyz ").map((c) => c.call)).toEqual(["OH3XYZ"]);
    expect(matching(list, "")).toHaveLength(3);
    expect(matching(list, "zzz")).toEqual([]);
  });
});

describe("recipients", () => {
  it("adds a call that is a call, is not the gateway and is not there yet", () => {
    expect(addable("oh2abc-9", [])).toBe(true);
    expect(addable("OH2ABC", ["OH2ABC"])).toBe(false);
    expect(addable("not a call", [])).toBe(false);
    expect(addable("EMAIL-2", [])).toBe(false);
  });

  it("is the calls picked and then the one typed, once each", () => {
    expect(recipientsOf(["OH2AAA", "OH2BBB"], " oh2ccc ")).toEqual(["OH2AAA", "OH2BBB", "OH2CCC"]);
    expect(recipientsOf(["OH2AAA"], "oh2aaa")).toEqual(["OH2AAA"]);
    expect(recipientsOf(["OH2AAA"], "")).toEqual(["OH2AAA"]);
    expect(recipientsOf([], "OH2RDG")).toEqual(["OH2RDG"]);
  });

  it("has Send on for a recipient and a text that fits, and off for a bad call in To, no recipient, no text or no TNC", () => {
    expect(canSendAll(true, ["OH2AAA"], "", "Hi")).toBe(true);
    expect(canSendAll(true, [], "OH2RDG", "Hi")).toBe(true);
    expect(canSendAll(true, ["OH2AAA"], "oops!", "Hi")).toBe(false);
    expect(canSendAll(true, ["OH2AAA"], "EMAIL-2", "Hi")).toBe(false);
    expect(canSendAll(true, [], "", "Hi")).toBe(false);
    expect(canSendAll(true, ["OH2AAA"], "", " ")).toBe(false);
    expect(canSendAll(true, ["OH2AAA"], "", "x".repeat(68))).toBe(false);
    expect(canSendAll(false, ["OH2AAA"], "", "Hi")).toBe(false);
  });
});
