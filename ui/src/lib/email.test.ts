import { describe, expect, it } from "vitest";
import {
  ADDRESSES_KEPT,
  GET_HELD,
  canSendEmail,
  emailBytesLeft,
  emailLine,
  forgetAddress,
  parseAddresses,
  rememberAddress,
  listShortcuts,
  removeShortcut,
  validShortcut,
} from "@/lib/email";

describe("the line to the gateway", () => {
  it("is the addressee, a space and the text", () => {
    expect(emailLine("jane@example.com", "Hello")).toBe("jane@example.com Hello");
    expect(emailLine(" me ", "Hello")).toBe("me Hello");
  });

  it("counts the addressee, the space and the text of the 67 bytes, in UTF-8", () => {
    expect(emailBytesLeft("", "")).toBe(66);
    expect(emailBytesLeft("me", "Hello")).toBe(67 - 8);
    expect(emailBytesLeft("jane@example.com", "x".repeat(50))).toBe(0);
    expect(emailBytesLeft("jane@example.com", "x".repeat(49) + "å")).toBe(-1);
    expect(emailBytesLeft("jörg@example.com", "Hello")).toBe(67 - 17 - 1 - 5);
  });
});

describe("canSendEmail", () => {
  it("is on with the TNC connected, an addressee and a text that fit", () => {
    expect(canSendEmail(true, "jane@example.com", "Hello")).toBe(true);
    expect(canSendEmail(true, "me", "x".repeat(64))).toBe(true);
  });

  it("is off with the TNC not connected, with no addressee, with no text, or with an addressee of two words", () => {
    expect(canSendEmail(false, "me", "Hello")).toBe(false);
    expect(canSendEmail(true, "", "Hello")).toBe(false);
    expect(canSendEmail(true, "   ", "Hello")).toBe(false);
    expect(canSendEmail(true, "me", "")).toBe(false);
    expect(canSendEmail(true, "me", "   ")).toBe(false);
    expect(canSendEmail(true, "me too", "Hello")).toBe(false);
  });

  it("is off when the line passes 67 bytes, and on at exactly 67", () => {
    expect(canSendEmail(true, "me", "x".repeat(64))).toBe(true);
    expect(canSendEmail(true, "me", "x".repeat(65))).toBe(false);
    expect(canSendEmail(true, "me", "x".repeat(63) + "å")).toBe(false);
  });
});

describe("the gateway's commands", () => {
  it("are name L, name R and get", () => {
    expect(listShortcuts("me")).toBe("me L");
    expect(listShortcuts(" me ")).toBe("me L");
    expect(removeShortcut("jane")).toBe("jane R");
    expect(removeShortcut(" jane ")).toBe("jane R");
    expect(GET_HELD).toBe("get");
  });

  it("take a shortcut that is letters and digits", () => {
    expect([validShortcut("jane"), validShortcut("Me2"), validShortcut(" me "), validShortcut(""), validShortcut("a b"), validShortcut("a@b.c")]).toEqual([
      true,
      true,
      true,
      false,
      false,
      false,
    ]);
  });
});

describe("the addressees used before", () => {
  it("puts the newest first, once, whatever the letters", () => {
    expect(rememberAddress([], "me")).toEqual(["me"]);
    expect(rememberAddress(["me", "a@b.c"], "a@b.c")).toEqual(["a@b.c", "me"]);
    expect(rememberAddress(["me", "Jane"], "jane")).toEqual(["jane", "me"]);
    expect(rememberAddress(["me"], "  ")).toEqual(["me"]);
  });

  it("keeps at most ADDRESSES_KEPT, dropping the oldest", () => {
    let list: string[] = [];
    for (let i = 0; i < ADDRESSES_KEPT + 3; i++) list = rememberAddress(list, `n${i}`);
    expect(list).toHaveLength(ADDRESSES_KEPT);
    expect(list[0]).toBe(`n${ADDRESSES_KEPT + 2}`);
    expect(list).not.toContain("n0");
  });

  it("forgets one and leaves the rest in order", () => {
    expect(forgetAddress(["c", "b", "a"], "b")).toEqual(["c", "a"]);
    expect(forgetAddress(["a"], "x")).toEqual(["a"]);
  });

  it("reads what was stored and nothing wrong", () => {
    expect(parseAddresses('["a@b.c","me"]')).toEqual(["a@b.c", "me"]);
    expect(parseAddresses(null)).toEqual([]);
    expect(parseAddresses("not json")).toEqual([]);
    expect(parseAddresses('{"a":1}')).toEqual([]);
    expect(parseAddresses('["a", 3, "", null, "b"]')).toEqual(["a", "b"]);
  });
});
