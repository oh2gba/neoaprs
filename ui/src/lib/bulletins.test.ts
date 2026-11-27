import { describe, expect, it } from "vitest";
import {
  POST_KINDS,
  canPost,
  freeSlot,
  groupOf,
  groupOk,
  kindTitle,
  newCount,
  newestFirstHeard,
  ownEntries,
  ownMeta,
  postCommand,
  rememberedHours,
  sections,
  sentForChoices,
  sentForText,
  targetOf,
  textOk,
  heardText,
  type PostDraft,
} from "@/lib/bulletins";
import { LIMITS } from "@/protocol/lists";
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
    const rows = [
      bulletin("BLN2", { last_heard: same }),
      bulletin("BLN1", { sender: "OH2ZZZ", last_heard: same }),
      bulletin("BLN1", { last_heard: same }),
    ];
    expect(sections(rows)[0]?.rows.map((r) => `${r.sender}/${r.slot}`)).toEqual([
      "OH2XYZ/BLN1",
      "OH2XYZ/BLN2",
      "OH2ZZZ/BLN1",
    ]);
  });
});

describe("targetOf and heardText", () => {
  it("calls a row by its group when it has one, else by its slot", () => {
    expect(targetOf(bulletin("BLN3HAMS", { group: "HAMS", kind: "group" }))).toBe("HAMS");
    expect(targetOf(bulletin("BLN1"))).toBe("BLN1");
    expect(targetOf(bulletin("QST", { kind: "group" }))).toBe("QST");
  });
  it("counts the hearings in words, with how long ago the last was", () => {
    const now = Date.parse("2026-10-24T12:00:00Z");
    const last = "2026-10-24T11:57:00Z";
    expect([1, 2, 12].map((n) => heardText(n, last, now))).toEqual([
      "heard once, 3 min ago",
      "heard 2 times, 3 min ago",
      "heard 12 times, 3 min ago",
    ]);
  });
});

describe("newCount and newestFirstHeard", () => {
  const rows = [
    bulletin("BLN1", { first_heard: ago(600) }),
    bulletin("BLN2", { first_heard: ago(300) }),
    bulletin("BLN3", { first_heard: ago(30) }),
  ];
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
    const own = ownBulletin("BLN3HAMS", {
      kind: "group",
      group: "HAMS",
      sent: 3,
      last_sent_at: ago(30),
      posted_at: ago(900),
    });
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
    const rows = [
      bulletin("BLN1", { last_heard: ago(900) }),
      ...ownEntries([ownBulletin("BLN2", { last_sent_at: ago(60) })], "OH2GBA"),
    ];
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
  const draft = (extra: Partial<PostDraft> = {}): PostDraft => ({
    kind: "bulletin",
    hours: null,
    group: "",
    text: "Road closed",
    ...extra,
  });
  const ours = (...slots: string[]) => new Map(slots.map((slot) => [slot, ownBulletin(slot)]));
  const digits = [..."0123456789"].map((c) => `BLN${c}`);
  const letters = [..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"].map((c) => `BLN${c}`);

  it("has the three kinds by name only, with no number in it", () => {
    expect(POST_KINDS).toEqual(["bulletin", "announcement", "group"]);
    expect(POST_KINDS.map(kindTitle)).toEqual(["Bulletin", "Announcement", "Group bulletin"]);
  });

  it("offers the daemon's Sent for choices, an announcement's in days", () => {
    expect(sentForChoices("bulletin")).toEqual(LIMITS.bulletin.hours);
    expect(sentForChoices("group")).toEqual(LIMITS.bulletin.hours);
    expect(sentForChoices("announcement")).toEqual(LIMITS.bulletin.announcementHours);
    expect(sentForText("bulletin", 1)).toBe("1 hour");
    expect(sentForText("group", 12)).toBe("12 hours");
    expect(sentForText("announcement", 24)).toBe("1 day");
    expect(sentForText("announcement", 168)).toBe("7 days");
  });

  it("starts Sent for at the station's choice of the kind, else the daemon's default", () => {
    const station = { bulletin: 8, announcement: 168, group: 2 };
    expect(POST_KINDS.map((kind) => rememberedHours(kind, station))).toEqual([8, 168, 2]);
    expect(POST_KINDS.map((kind) => rememberedHours(kind, undefined))).toEqual([4, 72, 4]);
    expect(rememberedHours("bulletin", { bulletin: 5, announcement: 4, group: 4 })).toBe(4);
    expect(rememberedHours("announcement", { bulletin: 5, announcement: 4, group: 4 })).toBe(72);
  });

  it("takes the lowest free number or letter of the kind, of the group for a group bulletin", () => {
    expect(freeSlot("bulletin", "", [])).toBe("BLN0");
    expect(freeSlot("bulletin", "", ["BLN0", "BLN2"])).toBe("BLN1");
    expect(freeSlot("bulletin", "", digits)).toBeNull();
    expect(freeSlot("announcement", "", digits)).toBe("BLNA");
    expect(freeSlot("announcement", "", letters)).toBeNull();
    expect(freeSlot("group", " hams ", ["BLN0HAMS", "BLN0WX", "BLN1"])).toBe("BLN1HAMS");
    expect(freeSlot("group", "", [])).toBeNull();
  });

  it("takes a group of one to five letters and digits, in any case", () => {
    expect([groupOk("HAMS"), groupOk("wx"), groupOk("12345"), groupOk("")]).toEqual([true, true, true, false]);
    expect([groupOk("TOOLONG"), groupOk("A B"), groupOk("A-B")]).toEqual([false, false, false]);
    expect(groupOf(" wx ")).toBe("WX");
  });

  it("takes printable ASCII up to 67 characters without | ~ {", () => {
    expect([textOk("Snow expected in Tampa RSN"), textOk("x".repeat(67)), textOk(" padded ")]).toEqual([
      true,
      true,
      true,
    ]);
    expect([
      textOk(""),
      textOk("   "),
      textOk("x".repeat(68)),
      textOk("a|b"),
      textOk("a~b"),
      textOk("a{b"),
      textOk("åäö"),
      textOk("a\tb"),
    ]).toEqual(Array<boolean>(8).fill(false));
  });

  it("is ready with a text that fits, for a group bulletin a group, and a free slot among fewer than the most of ours", () => {
    expect(canPost(draft(), ours())).toBe(true);
    expect(canPost(draft({ text: "" }), ours())).toBe(false);
    expect(canPost(draft({ kind: "group", group: "" }), ours())).toBe(false);
    expect(canPost(draft({ kind: "group", group: "WX" }), ours(...digits))).toBe(true);
    expect(canPost(draft(), ours(...digits)), "every number taken, an ended one too").toBe(false);
    expect(canPost(draft({ kind: "announcement" }), ours(...digits))).toBe(true);
    const full = ours(...digits.slice(0, 9), ...letters, "BLN0HAMS");
    expect(full.size).toBe(LIMITS.bulletin.postedMax);
    expect(canPost(draft(), full), "a number is free, but 36 are posted").toBe(false);
  });

  it("makes the command with the kind, the group of a group bulletin alone, the text stripped and the hours", () => {
    expect(postCommand(draft({ kind: "group", group: "hams", text: " Net tonight " }), 2, ours())).toEqual({
      cmd: "bulletin_post",
      kind: "group",
      group: "HAMS",
      text: "Net tonight",
      hours: 2,
    });
    expect(postCommand(draft({ group: "ignored" }), 4, ours(), [1, 3])).toEqual({
      cmd: "bulletin_post",
      kind: "bulletin",
      text: "Road closed",
      hours: 4,
      radios: [1, 3],
    });
    expect(postCommand(draft({ text: "" }), 4, ours())).toBeNull();
    expect(postCommand(draft(), 4, ours(...digits))).toBeNull();
  });
});
