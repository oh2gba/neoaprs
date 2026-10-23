import { describe, expect, it } from "vitest";
import {
  COMMENT_MAX,
  COMMENT_MAX_MOTION,
  commentLimit,
  draftOf,
  draftProblems,
  draftReady,
  emptyDraft,
  moveCommand,
  nameProblem,
  objectCommand,
  sentText,
  stateText,
  wrapLongitude,
  type ObjectDraft,
} from "@/lib/ownobjects";
import { NOW, ownObject } from "@/test/fixtures";

const ready = (extra: Partial<ObjectDraft> = {}): ObjectDraft => ({ ...emptyDraft({ lat: 60.17, lon: 24.94 }), name: "LEADER", ...extra });

describe("emptyDraft and draftOf", () => {
  it("starts a new object where we are, as a car, with no name", () => {
    expect(emptyDraft({ lat: 60.17, lon: 24.94 })).toEqual({
      name: "",
      kind: "object",
      symbol: "/>",
      lat: "60.17",
      lon: "24.94",
      comment: "",
      course: "",
      speed: "",
      path: "",
    });
    expect(emptyDraft(null)).toMatchObject({ lat: "", lon: "" });
  });

  it("is what the daemon has of an object, written as it is typed", () => {
    const row = ownObject("LEADER", {
      symbol_table: "\\",
      symbol_code: "l",
      comment: "Rescue 1",
      course_deg: 88,
      speed_kmh: 66.672,
      path: "WIDE2-1",
      lat: 60.1700001,
    });
    expect(draftOf(row)).toEqual({
      name: "LEADER",
      kind: "object",
      symbol: "\\l",
      lat: "60.17",
      lon: "24.9",
      comment: "Rescue 1",
      course: "88",
      speed: "66.7",
      path: "WIDE2-1",
    });
    expect(draftOf(ownObject("AID", { kind: "item" }))).toMatchObject({ kind: "item", course: "", speed: "", path: "" });
  });
});

describe("nameProblem", () => {
  it("has none for a name of the right length without the characters the packet cannot carry, and none for an empty one", () => {
    for (const name of ["", "A", "123456789", "Rescue-1", "a b"]) expect(nameProblem(name, "object"), name).toBe("");
    expect(nameProblem("ABC", "item")).toBe("");
  });

  it("refuses a blank at an end, ! _ | ~, anything but printable ASCII and more than nine characters", () => {
    for (const name of [" A", "A ", "A!B", "A_B", "A|B", "A~B", "Ä", "tab\t"]) expect(nameProblem(name, "object"), name).not.toBe("");
    expect(nameProblem("TENCHARSXX", "object")).toBe("At most 9 characters");
  });

  it("wants three characters for an item", () => {
    expect(nameProblem("AB", "item")).toBe("An item has 3 to 9 characters");
    expect(nameProblem("AB", "object")).toBe("");
  });
});

describe("draftProblems and draftReady", () => {
  it("says nothing of a draft that is right, and of one whose fields are still empty", () => {
    expect(draftProblems(ready())).toEqual({});
    expect(draftProblems(emptyDraft(null))).toEqual({});
    expect(draftReady(ready())).toBe(true);
    expect(draftReady(emptyDraft(null))).toBe(false);
  });

  it("needs a name, a symbol of two characters and a position", () => {
    expect(draftReady(ready({ name: "" }))).toBe(false);
    expect(draftReady(ready({ symbol: "/" }))).toBe(false);
    expect(draftReady(ready({ lat: "" }))).toBe(false);
    expect(draftReady(ready({ lon: "" }))).toBe(false);
  });

  it("names each field that is wrong", () => {
    const problems = draftProblems(
      ready({ name: "A!", lat: "91", lon: "x", symbol: "!!", course: "360", speed: "-1", path: "A,B,C,D,E,F,G,H,I", comment: "a|b" }),
    );
    expect(Object.keys(problems).sort()).toEqual(["comment", "course", "lat", "lon", "name", "path", "speed", "symbol"]);
    expect(problems.lat).toBe("Between -90 and 90");
    expect(problems.lon).toBe("Not a number");
    expect(problems.course).toBe("0 to 359 degrees");
    expect(draftReady(ready({ lat: "91" }))).toBe(false);
  });

  it("takes a comma as the decimal point and a course of 0, and a speed up to 1850", () => {
    expect(draftProblems(ready({ lat: "60,17", course: "0", speed: "1850" }))).toEqual({});
    expect(draftProblems(ready({ speed: "1851" })).speed).toBe("0 to 1850 km/h");
    expect(draftProblems(ready({ course: "12.5" })).course).toBe("0 to 359 degrees");
  });

  it("allows 43 characters of comment, 36 behind a course or a speed", () => {
    expect(commentLimit(ready())).toBe(COMMENT_MAX);
    expect(commentLimit(ready({ course: "10" }))).toBe(COMMENT_MAX_MOTION);
    expect(commentLimit(ready({ speed: "5" }))).toBe(COMMENT_MAX_MOTION);
    expect(draftProblems(ready({ comment: "x".repeat(43) }))).toEqual({});
    expect(draftProblems(ready({ comment: "x".repeat(44) })).comment).toBe("At most 43 characters");
    expect(draftProblems(ready({ comment: "x".repeat(37), speed: "5" })).comment).toBe("At most 36 characters");
  });

  it("reads a path as the settings do: up to eight calls separated by commas, empty for the beacon's", () => {
    expect(draftProblems(ready({ path: "wide1-1, wide2-1" }))).toEqual({});
    expect(draftProblems(ready({ path: "WIDE1-1,,BAD CALL" })).path).toBe("Calls separated by commas, at most 8");
  });
});

describe("objectCommand", () => {
  it("is the command that makes the object, every field as the daemon takes it", () => {
    expect(objectCommand(ready({ kind: "item", symbol: "\\+", comment: " First aid ", course: "90", speed: "12,5", path: "wide2-1" }))).toEqual({
      cmd: "object_set",
      name: "LEADER",
      kind: "item",
      lat: 60.17,
      lon: 24.94,
      symbol_table: "\\",
      symbol_code: "+",
      comment: "First aid",
      course_deg: 90,
      speed_kmh: 12.5,
      path: "WIDE2-1",
    });
  });

  it("leaves the course, the speed and the path null when they are empty", () => {
    expect(objectCommand(ready())).toMatchObject({ course_deg: null, speed_kmh: null, path: null, comment: "" });
    expect(objectCommand(ready({ course: "0" }))).toMatchObject({ course_deg: 0 });
  });

  it("is none while the draft is not ready", () => {
    expect(objectCommand(ready({ name: "" }))).toBeNull();
    expect(objectCommand(ready({ lat: "95" }))).toBeNull();
  });
});

describe("moveCommand", () => {
  it("is the object as it is with the place new, to five decimals", () => {
    const row = ownObject("LEADER", { comment: "Rescue 1", course_deg: 88, speed_kmh: 40, path: "WIDE2-1" });
    expect(moveCommand(row, 60.123456789, 24.987654321)).toEqual({
      cmd: "object_set",
      name: "LEADER",
      kind: "object",
      lat: 60.12346,
      lon: 24.98765,
      symbol_table: "/",
      symbol_code: ">",
      comment: "Rescue 1",
      course_deg: 88,
      speed_kmh: 40,
      path: "WIDE2-1",
    });
  });

  it("brings a longitude of a map that was wrapped round into -180 to 180", () => {
    expect(wrapLongitude(190)).toBe(-170);
    expect(wrapLongitude(-190)).toBe(170);
    expect(wrapLongitude(24.5)).toBe(24.5);
    expect(moveCommand(ownObject("A"), 0, 361).lon).toBe(1);
  });
});

describe("stateText", () => {
  it("says how often it was sent and when it is sent next", () => {
    expect(stateText(ownObject("A", { sent: 2 }), NOW)).toBe("sent 2 times, next in 3 min");
    expect(stateText(ownObject("A", { sent: 1, next_at: new Date(NOW + 40_000).toISOString() }), NOW)).toBe("sent once, next in 40 s");
  });

  it("says waiting for one that is overdue (the call is not set, or the radio is away) and not for one that is due this second", () => {
    expect(stateText(ownObject("A", { sent: 0, last_sent_at: null, next_at: new Date(NOW - 60_000).toISOString() }), NOW)).toBe("not sent yet, waiting");
    expect(stateText(ownObject("A", { sent: 0, next_at: new Date(NOW - 1000).toISOString() }), NOW)).toBe("not sent yet, next now");
  });

  it("says killing, with how often the kill was sent", () => {
    expect(stateText(ownObject("A", { state: "killing", sent: 1 }), NOW)).toBe("killing, sent once");
  });

  it("words the count of what was sent", () => {
    expect([0, 1, 5].map(sentText)).toEqual(["not sent yet", "sent once", "sent 5 times"]);
  });
});
