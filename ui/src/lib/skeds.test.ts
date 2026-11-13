import { describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import {
  DAYS,
  NOTE_MAX,
  TIMES,
  callsOf,
  dayChoices,
  dialOf,
  draftOk,
  ended,
  groups,
  hasCall,
  instants,
  localText,
  mayPostAs,
  newCount,
  noteLeft,
  noteOf,
  postCommand,
  startDraft,
  tooFar,
  whenText,
  type SkedDraft,
} from "@/lib/skeds";
import { NOW, sked, skedsState } from "@/test/fixtures";

// The fixtures' time is Wednesday 21 October 2026, 12:00 UTC.
const FREQUENCIES = skedsState().frequencies;
const draft = (extra: Partial<SkedDraft> = {}): SkedDraft => ({
  day: "2026-10-22",
  from: "18:00",
  to: "20:00",
  dial: "7.0541 MHz USB",
  typed: false,
  note: "",
  ...extra,
});
const at = (hours: number) => new Date(NOW + hours * 3_600_000).toISOString().slice(0, 19) + "Z";

describe("the times of the form", () => {
  it("are the 48 half hours of a day", () => {
    expect(TIMES).toHaveLength(48);
    expect(TIMES[0]).toBe("00:00");
    expect(TIMES[1]).toBe("00:30");
    expect(TIMES.at(-1)).toBe("23:30");
  });

  it("makes To after From the same day, and To at or before From the next day", () => {
    expect(instants(draft())).toEqual({ from: Date.parse("2026-10-22T18:00:00Z"), to: Date.parse("2026-10-22T20:00:00Z") });
    expect(instants(draft({ from: "22:00", to: "02:00" }))).toEqual({ from: Date.parse("2026-10-22T22:00:00Z"), to: Date.parse("2026-10-23T02:00:00Z") });
    expect(instants(draft({ from: "18:00", to: "18:00" }))).toEqual({ from: Date.parse("2026-10-22T18:00:00Z"), to: Date.parse("2026-10-23T18:00:00Z") });
    expect(instants(draft({ from: "23:30", to: "00:00" }))?.to).toBe(Date.parse("2026-10-23T00:00:00Z"));
  });

  it("is never longer than 24 hours, whatever From and To are", () => {
    for (const from of TIMES) {
      for (const to of TIMES) {
        const span = (instants(draft({ from, to }))?.to ?? 0) - (instants(draft({ from, to }))?.from ?? 0);
        expect(span).toBeGreaterThan(0);
        expect(span).toBeLessThanOrEqual(24 * 3_600_000);
      }
    }
  });

  it("is none for a day or a time that is not one of the choices", () => {
    expect(instants(draft({ day: "" }))).toBeNull();
    expect(instants(draft({ day: "22 Oct" }))).toBeNull();
    expect(instants(draft({ from: "18:15" }))).toBeNull();
    expect(instants(draft({ to: "24:00" }))).toBeNull();
  });
});

describe("the days of the form", () => {
  it("are the next 30 UTC days, today first", () => {
    const days = dayChoices(NOW);
    expect(days).toHaveLength(DAYS);
    expect(days[0]?.value).toBe("2026-10-21");
    expect(days[1]?.value).toBe("2026-10-22");
    expect(days.at(-1)?.value).toBe("2026-11-19");
  });

  it("are the UTC days even when the UTC day is not the viewer's", () => {
    expect(dayChoices(Date.parse("2026-10-21T23:59:00Z"))[0]?.value).toBe("2026-10-21");
    expect(dayChoices(Date.parse("2026-10-22T00:00:00Z"))[0]?.value).toBe("2026-10-22");
  });

  it("are written in the language of the page, weekday first", () => {
    setLocale("en");
    expect(dayChoices(NOW)[0]?.label).toBe("Wed 21 Oct");
    setLocale("de");
    expect(dayChoices(NOW)[0]?.label).toMatch(/^Mi/);
    setLocale("en");
  });

  it("never offer a start more than 30 days after any moment of today, at the latest half hour of the last day", () => {
    for (const now of [Date.parse("2026-10-21T00:00:00Z"), NOW, Date.parse("2026-10-21T23:59:59Z")]) {
      const last = dayChoices(now).at(-1)?.value ?? "";
      expect(tooFar(draft({ day: last, from: "23:30", to: "00:30" }), now)).toBe(false);
    }
    expect(tooFar(draft({ day: "2026-11-20", from: "12:30" }), NOW)).toBe(true); // (the day after the last the form offers, half an hour past the 30 days)
    expect(tooFar(draft({ day: "2026-11-20", from: "12:00" }), NOW)).toBe(false);
  });
});

describe("the form as it opens", () => {
  it("starts at the next half hour for an hour, on the first dial the project suggests", () => {
    expect(startDraft(NOW, FREQUENCIES)).toEqual({ day: "2026-10-21", from: "12:00", to: "13:00", dial: "7.0541 MHz USB", typed: false, note: "" });
    expect(startDraft(NOW + 60_000, FREQUENCIES)).toMatchObject({ from: "12:30", to: "13:30" });
  });

  it("goes over midnight to the next UTC day", () => {
    expect(startDraft(Date.parse("2026-10-21T23:40:00Z"), FREQUENCIES)).toMatchObject({ day: "2026-10-22", from: "00:00", to: "01:00" });
  });

  it("asks for a dial to be typed where the project suggests none", () => {
    expect(startDraft(NOW, [])).toMatchObject({ dial: "", typed: true });
  });
});

describe("the dial", () => {
  it("is written 7.0541 MHz USB, and what is typed in another way of writing it is put in that", () => {
    expect(dialOf("7.0541 MHz USB")).toBe("7.0541 MHz USB");
    expect(dialOf("  14.107 mhz usb ")).toBe("14.107 MHz USB");
    expect(dialOf("7.0541MHz lsb")).toBe("7.0541 MHz LSB");
    expect(dialOf("7.0541   MHz   USB")).toBe("7.0541 MHz USB");
  });

  it("is none for text that is not one", () => {
    for (const text of [
      "",
      "7.0541",
      "7.0541 MHz",
      "7.0541 MHz FM",
      "7 MHz USB",
      "7.05 MHz USB",
      "7.05412 MHz USB",
      "107.0541 MHz USB",
      "7,0541 MHz USB",
      "7.0541 kHz USB",
    ]) {
      expect(dialOf(text), text).toBeNull();
    }
  });
});

describe("the note", () => {
  it("fits at 80 characters once trimmed, counted as characters", () => {
    expect(NOTE_MAX).toBe(80);
    expect(noteLeft("")).toBe(80);
    expect(noteLeft("  Mercury, 10 W ")).toBe(80 - 13);
    expect(noteLeft("x".repeat(81))).toBe(-1);
    expect(noteLeft("é".repeat(80))).toBe(0);
    expect(noteLeft("😀".repeat(80))).toBe(0);
  });
});

describe("whether the form is right", () => {
  it("is right with a day, times, a dial and a note that fit, and the sked not ended", () => {
    expect(draftOk(draft(), NOW)).toBe(true);
    expect(draftOk(draft({ note: "Mercury, 10 W" }), NOW)).toBe(true);
    expect(draftOk(draft({ dial: "14.1070 MHz USB" }), NOW)).toBe(true);
  });

  it("is not right for a sked that has ended, but is for one that is running", () => {
    expect(ended(draft({ day: "2026-10-21", from: "08:00", to: "10:00" }), NOW)).toBe(true);
    expect(draftOk(draft({ day: "2026-10-21", from: "08:00", to: "10:00" }), NOW)).toBe(false);
    expect(draftOk(draft({ day: "2026-10-21", from: "08:00", to: "13:00" }), NOW)).toBe(true);
    expect(draftOk(draft({ day: "2026-10-21", from: "08:00", to: "12:00" }), NOW)).toBe(false); // (it ends this moment)
  });

  it("takes To at or before From of today as the next day, which has not ended", () => {
    expect(draftOk(draft({ day: "2026-10-21", from: "18:00", to: "02:00" }), NOW)).toBe(true);
    expect(draftOk(draft({ day: "2026-10-21", from: "08:00", to: "08:00" }), NOW)).toBe(true); // (24 hours from 08:00 reaches 08:00 tomorrow)
  });

  it("is not right with a dial that is not of the form, a typed one included, or a note over 80", () => {
    expect(draftOk(draft({ dial: "" }), NOW)).toBe(false);
    expect(draftOk(draft({ typed: true, dial: "7.0541" }), NOW)).toBe(false);
    expect(draftOk(draft({ typed: true, dial: "7.0541 mhz usb" }), NOW)).toBe(true);
    expect(draftOk(draft({ note: "x".repeat(81) }), NOW)).toBe(false);
    expect(draftOk(draft({ note: "x".repeat(80) }), NOW)).toBe(true);
  });

  it("is not right for a day beyond the 30 the board takes", () => {
    expect(draftOk(draft({ day: "2026-11-20", from: "12:30" }), NOW)).toBe(false);
  });
});

describe("the command that posts", () => {
  it("has the two instants in UTC to the second, the dial in the form of the board and the trimmed note, and never the call", () => {
    expect(postCommand(draft({ typed: true, dial: "7.0541 mhz usb", note: "  Mercury, 10 W " }), NOW)).toEqual({
      cmd: "sked_post",
      from: "2026-10-22T18:00:00Z",
      to: "2026-10-22T20:00:00Z",
      dial: "7.0541 MHz USB",
      note: "Mercury, 10 W",
    });
  });

  it("has the end on the next day for a To that is not after From", () => {
    expect(postCommand(draft({ from: "22:00", to: "02:00" }), NOW)).toMatchObject({ from: "2026-10-22T22:00:00Z", to: "2026-10-23T02:00:00Z" });
  });

  it("is none while the form is not right", () => {
    expect(postCommand(draft({ day: "2026-10-21", from: "08:00", to: "10:00" }), NOW)).toBeNull();
    expect(postCommand(draft({ dial: "x" }), NOW)).toBeNull();
    expect(postCommand(draft({ day: "" }), NOW)).toBeNull();
  });
});

describe("the call a sked may be posted under", () => {
  it("is an amateur's call, set, and no placeholder", () => {
    expect(mayPostAs("OH2GBA")).toBe(true);
    expect(mayPostAs("OH2GBA-7")).toBe(true);
    expect(mayPostAs("N0CALL")).toBe(false);
    expect(mayPostAs("")).toBe(false);
    expect(mayPostAs(null)).toBe(false);
    expect(mayPostAs("NOT A CALL")).toBe(false);
  });
});

describe("the rows of the board", () => {
  it("are the skeds to come in the order of their start, then end", () => {
    const rows = [sked("c", { from: at(30), to: at(32) }), sked("a", { from: at(2), to: at(3) }), sked("b", { from: at(2), to: at(4) })];
    expect(groups(rows, NOW).map((g) => g.rows[0]?.id)).toEqual(["a", "b", "c"]);
  });

  it("leave out a sked that has ended by the page's clock, and keep one that is running", () => {
    const rows = [sked("old", { from: at(-3), to: at(-1) }), sked("now", { from: at(-1), to: at(1) }), sked("end", { from: at(-2), to: at(0) })];
    expect(groups(rows, NOW).map((g) => g.rows[0]?.id)).toEqual(["now"]);
    expect(groups([sked("x", { to: "not a time" })], NOW)).toEqual([]);
  });

  it("are one row for skeds with the same times and dial, which lists the calls, and two for another dial or another end", () => {
    const rows = [
      sked("a", { call: "OH2AAA" }),
      sked("b", { call: "OH2BBB", ours: true }),
      sked("c", { call: "OH2CCC", dial: "14.1070 MHz USB" }),
      sked("d", { call: "OH2DDD", to: at(5) }),
    ];
    const found = groups(rows, NOW);
    expect(found).toHaveLength(3);
    const shared = found.find((g) => g.rows.length === 2);
    expect(callsOf(shared!)).toEqual(["OH2AAA", "OH2BBB"]);
    expect(shared?.ours.map((r) => r.id)).toEqual(["b"]);
    expect(found.filter((g) => g.rows.length === 1).map((g) => g.ours)).toEqual([[], []]);
  });

  it("know whether a call is on the row, our call without an SSID of 0 as the board has it", () => {
    const [row] = groups([sked("a", { call: "OH2GBA" }), sked("b", { call: "OH2XYZ-7" })], NOW);
    expect(hasCall(row, "OH2GBA")).toBe(true);
    expect(hasCall(row, "OH2GBA-0")).toBe(true);
    expect(hasCall(row, "oh2xyz-7")).toBe(true);
    expect(hasCall(row, "OH2XYZ")).toBe(false);
    expect(hasCall(row, null)).toBe(false);
  });

  it("have the note on one line: the one note, or each with its call when there are several, and none when nobody wrote one", () => {
    expect(noteOf(groups([sked("a", { note: "Mercury, 10 W" })], NOW)[0])).toBe("Mercury, 10 W");
    expect(noteOf(groups([sked("a")], NOW)[0])).toBe("");
    expect(
      noteOf(groups([sked("a", { call: "OH2AAA", note: "one" }), sked("b", { call: "OH2BBB", note: "" }), sked("c", { call: "OH2CCC", note: "two" })], NOW)[0]),
    ).toBe("OH2AAA: one; OH2CCC: two");
    expect(noteOf(groups([sked("a", { call: "OH2AAA", note: "one" }), sked("b", { call: "OH2BBB" })], NOW)[0])).toBe("OH2AAA: one");
  });
});

describe("the words of a row", () => {
  it("write the time in UTC, the end with its day when it is another", () => {
    setLocale("en");
    expect(whenText("2026-11-14T18:00:00Z", "2026-11-14T20:00:00Z")).toBe("Sat 14 Nov 18:00 to 20:00 UTC");
    expect(whenText("2026-11-14T22:00:00Z", "2026-11-15T02:00:00Z")).toBe("Sat 14 Nov 22:00 to Sun 15 Nov 02:00 UTC");
  });

  it("write the viewer's own time for the title", () => {
    const text = localText("2026-11-14T18:00:00Z", "2026-11-14T20:00:00Z");
    expect(text).toMatch(/^Your time: \w{3} \d{1,2} \w{3} \d{2}:\d{2} to (\w{3} \d{1,2} \w{3} )?\d{2}:\d{2}$/);
  });
});

describe("the skeds not seen", () => {
  it("are the ones of others whose id is not in the seen ones; ours never count", () => {
    const rows = [sked("a"), sked("b"), sked("c", { ours: true })];
    expect(newCount(rows, new Set())).toBe(2);
    expect(newCount(rows, new Set(["a"]))).toBe(1);
    expect(newCount(rows, new Set(["a", "b"]))).toBe(0);
  });
});
