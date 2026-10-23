import { describe, expect, it } from "vitest";
import { newCount, newestFirstHeard, sections, targetOf, timesText } from "@/lib/bulletins";
import { ago, bulletin } from "@/test/fixtures";

describe("sections", () => {
  it("groups the board into announcements, bulletins and group messages, each newest first", () => {
    const rows = [
      bulletin("BLN1", { last_heard: ago(300) }),
      bulletin("QST", { kind: "group", sender: "OH2ABC", last_heard: ago(10) }),
      bulletin("BLNA", { kind: "announcement", last_heard: ago(900) }),
      bulletin("BLN2", { last_heard: ago(60) }),
      bulletin("BLN3HAMS", { kind: "group", group: "HAMS", last_heard: ago(30) }),
    ];
    expect(sections(rows).map((s) => [s.title, s.rows.map((r) => r.slot)])).toEqual([
      ["Announcements", ["BLNA"]],
      ["Bulletins", ["BLN2", "BLN1"]],
      ["Group messages", ["QST", "BLN3HAMS"]],
    ]);
  });

  it("puts the weather service bulletins in a fourth section", () => {
    const rows = [bulletin("NWS-WARN", { kind: "nws", sender: "OH2NWS", last_heard: ago(10) }), bulletin("BLN1")];
    expect(sections(rows).map((s) => [s.title, s.rows.map((r) => r.slot)])).toEqual([
      ["Bulletins", ["BLN1"]],
      ["Weather service", ["NWS-WARN"]],
    ]);
  });

  it("leaves out a section with nothing in it, and is empty for an empty board", () => {
    expect(sections([bulletin("BLN1")]).map((s) => s.kind)).toEqual(["bulletin"]);
    expect(sections([])).toEqual([]);
  });

  it("puts rows heard at the same moment in the order of the sender and the slot", () => {
    const same = ago(60);
    const rows = [bulletin("BLN2", { last_heard: same }), bulletin("BLN1", { sender: "OH2ZZZ", last_heard: same }), bulletin("BLN1", { last_heard: same })];
    expect(sections(rows)[0]?.rows.map((r) => `${r.sender}/${r.slot}`)).toEqual(["OH2XYZ/BLN1", "OH2XYZ/BLN2", "OH2ZZZ/BLN1"]);
  });
});

describe("targetOf and timesText", () => {
  it("calls a row by its group when it has one, else by its slot", () => {
    expect(targetOf(bulletin("BLN3HAMS", { group: "HAMS", kind: "group" }))).toBe("HAMS");
    expect(targetOf(bulletin("BLN1"))).toBe("BLN1");
    expect(targetOf(bulletin("QST", { kind: "group" }))).toBe("QST");
  });
  it("counts the hearings in words", () => {
    expect([timesText(1), timesText(2), timesText(12)]).toEqual(["heard once", "heard 2 times", "heard 12 times"]);
  });
});

describe("newCount and newestFirstHeard", () => {
  const rows = [bulletin("BLN1", { first_heard: ago(600) }), bulletin("BLN2", { first_heard: ago(300) }), bulletin("BLN3", { first_heard: ago(30) })];
  it("counts the rows whose text was first heard after the time that was seen", () => {
    expect(newCount(rows, 0)).toBe(3);
    expect(newCount(rows, Date.parse(ago(400)))).toBe(2);
    expect(newCount(rows, Date.parse(ago(30)))).toBe(0);
    expect(newCount([], 0)).toBe(0);
  });
  it("finds the newest first hearing", () => {
    expect(newestFirstHeard(rows)).toBe(Date.parse(ago(30)));
    expect(newestFirstHeard([])).toBe(0);
    expect(newestFirstHeard([bulletin("BLN1", { first_heard: "garbage" })])).toBe(0);
  });
});
