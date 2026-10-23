import { describe, expect, it } from "vitest";
import {
  POST_KINDS,
  canPost,
  charsLeft,
  groupOf,
  groupOk,
  idsOf,
  newCount,
  newestFirstHeard,
  ownEntries,
  ownMeta,
  postCommand,
  sections,
  slotOf,
  targetOf,
  textOk,
  timesText,
  type PostDraft,
} from "@/lib/bulletins";
import { NOW, ago, bulletin, ownBulletin } from "@/test/fixtures";

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

describe("ownEntries and ownMeta", () => {
  it("writes our bulletins as rows of the board under our call, with what the daemon says of them kept", () => {
    const own = ownBulletin("BLN3HAMS", { kind: "group", group: "HAMS", sent: 3, last_sent_at: ago(30), posted_at: ago(900) });
    const [entry] = ownEntries([own], "OH2GBA");
    expect(entry).toMatchObject({
      sender: "OH2GBA",
      slot: "BLN3HAMS",
      group: "HAMS",
      kind: "group",
      text: own.text,
      first_heard: own.posted_at,
      last_heard: own.last_sent_at,
      times_heard: 3,
    });
    expect(entry?.own).toBe(own);
  });

  it("dates one that has not been sent yet by its posting", () => {
    const [entry] = ownEntries([ownBulletin("BLN1", { sent: 0, last_sent_at: null, posted_at: ago(20) })], "OH2GBA");
    expect(entry).toMatchObject({ last_heard: ago(20), times_heard: 1 });
  });

  it("sorts with the rest of the board, into its section", () => {
    const rows = [bulletin("BLN1", { last_heard: ago(900) }), ...ownEntries([ownBulletin("BLN2", { last_sent_at: ago(60) })], "OH2GBA")];
    expect(sections(rows)[0]?.rows.map((r) => r.slot)).toEqual(["BLN2", "BLN1"]);
  });

  it("says how often it was sent and when it goes out next, ended once the schedule is over", () => {
    expect(ownMeta(ownBulletin("BLN1", { sent: 2 }), NOW)).toBe("sent 2 times, next in 18 min");
    expect(ownMeta(ownBulletin("BLN1", { sent: 14, next_at: null }), NOW)).toBe("sent 14 times, ended");
    expect(ownMeta(ownBulletin("BLN1", { sent: 0, last_sent_at: null }), NOW)).toBe("not sent yet, next in 18 min");
    expect(ownMeta(ownBulletin("BLN1", { sent: 0, next_at: null }), NOW)).toBe("not sent yet");
  });
});

describe("posting", () => {
  const draft = (extra: Partial<PostDraft> = {}): PostDraft => ({ kind: "bulletin", id: "1", group: "", text: "Road closed", ...extra });

  it("has the three kinds, a bulletin and a group bulletin numbered and an announcement lettered", () => {
    expect(POST_KINDS.map((k) => k.kind)).toEqual(["bulletin", "announcement", "group"]);
    expect(idsOf("bulletin")).toBe("0123456789");
    expect(idsOf("group")).toBe("0123456789");
    expect(idsOf("announcement")).toHaveLength(26);
    expect(idsOf("announcement")[0]).toBe("A");
  });

  it("makes the slot: BLN and the identifier, and the group after it for a group bulletin", () => {
    expect(slotOf(draft())).toBe("BLN1");
    expect(slotOf(draft({ kind: "announcement", id: "Q" }))).toBe("BLNQ");
    expect(slotOf(draft({ kind: "group", id: "3", group: " hams " }))).toBe("BLN3HAMS");
    expect(slotOf(draft({ id: "7", group: "ignored" }))).toBe("BLN7");
  });

  it("takes a group of one to five letters and digits, in any case", () => {
    expect([groupOk("HAMS"), groupOk("wx"), groupOk("12345"), groupOk("")]).toEqual([true, true, true, false]);
    expect([groupOk("TOOLONG"), groupOk("A B"), groupOk("A-B")]).toEqual([false, false, false]);
    expect(groupOf(" wx ")).toBe("WX");
  });

  it("takes printable ASCII up to 67 characters without | ~ {", () => {
    expect([textOk("Snow expected in Tampa RSN"), textOk("x".repeat(67)), textOk(" padded ")]).toEqual([true, true, true]);
    expect([textOk(""), textOk("   "), textOk("x".repeat(68)), textOk("a|b"), textOk("a~b"), textOk("a{b"), textOk("åäö"), textOk("a\tb")]).toEqual(
      Array<boolean>(8).fill(false),
    );
    expect([charsLeft(""), charsLeft("x".repeat(60)), charsLeft("x".repeat(70))]).toEqual([67, 7, -3]);
  });

  it("is ready with a text that fits and, for a group bulletin, a group", () => {
    expect(canPost(draft())).toBe(true);
    expect(canPost(draft({ text: "" }))).toBe(false);
    expect(canPost(draft({ kind: "group", group: "" }))).toBe(false);
    expect(canPost(draft({ kind: "group", group: "WX", id: "4" }))).toBe(true);
    expect(canPost(draft({ kind: "announcement", id: "1" }))).toBe(false);
  });

  it("makes the command, with the text stripped, and none while it cannot be posted", () => {
    expect(postCommand(draft({ kind: "group", id: "3", group: "hams", text: " Net tonight " }))).toEqual({
      cmd: "bulletin_post",
      slot: "BLN3HAMS",
      text: "Net tonight",
    });
    expect(postCommand(draft({ text: "" }))).toBeNull();
  });
});
