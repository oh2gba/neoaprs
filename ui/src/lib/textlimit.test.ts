import { describe, expect, it } from "vitest";
import { bytes, characters, commentLimit, fitted, leftOf, settingLimit, templateLength, type TextLimit, trimmedCharacters, typedInto } from "@/lib/textlimit";
import vectors from "@/protocol/vectors.json";

const chars = (max: number): TextLimit => ({ max, measure: characters, kind: "characters" });
const inBytes = (max: number): TextLimit => ({ max, measure: bytes, kind: "bytes" });

describe("characters and bytes", () => {
  it("count as the daemon does: a character is a code point (Python's len), a byte one of its UTF-8", () => {
    expect(characters("abc")).toBe(3);
    expect(characters("ä")).toBe(1);
    expect(characters("😀")).toBe(1); // (two UTF-16 units in JavaScript, one character to Python)
    expect(bytes("ä")).toBe(2);
    expect(bytes("😀")).toBe(4);
  });
});

describe("leftOf", () => {
  it("is what is left of the limit, and how many are over (negative) for a text that is already longer", () => {
    expect(leftOf("", chars(43))).toBe(43);
    expect(leftOf("NeoAPRS", chars(43))).toBe(36);
    expect(leftOf("x".repeat(50), chars(43))).toBe(-7);
    expect(leftOf("  ab  ", { max: 5, measure: trimmedCharacters, kind: "characters" })).toBe(3);
  });
});

describe("typedInto", () => {
  const limit = chars(5);
  const field = (value: string) => {
    const input = document.createElement("input");
    document.body.append(input);
    input.value = value;
    return input;
  };
  const input = (target: HTMLInputElement, isComposing = false) => {
    const event = new InputEvent("input", { isComposing });
    target.dispatchEvent(event);
    return event;
  };

  it("cuts what is typed or pasted past the limit in the field itself, the caret at the end of what was kept", () => {
    const target = field("ab1234567");
    expect(typedInto(input(target), "ab", limit)).toBe("ab123");
    expect(target.value).toBe("ab123");
    expect(target.selectionStart).toBe(5);
    target.remove();
  });

  it("lets a keyboard that composes (an IME, a phone's word) finish, and fits what it composed against the text before it", () => {
    const target = field("abcに");
    expect(typedInto(input(target, true), "abc", limit)).toBe("abcに");
    target.value = "abcにほ";
    expect(typedInto(input(target, true), "abcに", limit)).toBe("abcにほ");
    target.value = "abc日本語";
    expect(typedInto(input(target, true), "abcにほ", limit)).toBe("abc日本語");
    expect(target.value).toBe("abc日本語");
    target.value = "abc日本語";
    expect(typedInto(new CompositionEvent("compositionend"), "abc日本語", limit)).toBe("abc日本語"); // (an event of no field changes nothing)
    const end = new CompositionEvent("compositionend");
    target.dispatchEvent(end);
    expect(typedInto(end, "abc日本語", limit)).toBe("abc日本");
    expect(target.value).toBe("abc日本");
    expect(typedInto(input(target), "abc日本", limit)).toBe("abc日本"); // (the input event that follows in some browsers)
    target.remove();
  });
});

describe("fitted", () => {
  it("keeps what fits as it is", () => {
    expect(fitted("abc", "abcd", chars(5))).toEqual({ text: "abcd" });
    expect(fitted("abcd", "abcde", chars(5))).toEqual({ text: "abcde" });
  });

  it("takes nothing more at the limit, wherever the caret is", () => {
    expect(fitted("abcde", "abcdef", chars(5))).toEqual({ text: "abcde", at: 5 });
    expect(fitted("abcde", "abXcde", chars(5))).toEqual({ text: "abcde", at: 2 });
  });

  it("cuts a paste longer than the room at the limit, keeping its start, and puts the caret at the end of what was kept", () => {
    expect(fitted("ab", "ab1234567", chars(5))).toEqual({ text: "ab123", at: 5 });
    expect(fitted("abyz", "ab123456yz", chars(6))).toEqual({ text: "ab12yz", at: 4 });
  });

  it("counts bytes where the daemon does: a letter of two bytes that does not fit whole is not taken", () => {
    expect(fitted("abcd", "abcdä", inBytes(5))).toEqual({ text: "abcd", at: 4 });
    expect(fitted("abc", "abcä", inBytes(5))).toEqual({ text: "abcä" });
    expect(fitted("", "ääa", inBytes(5))).toEqual({ text: "ääa" });
    expect(fitted("", "äää", inBytes(5))).toEqual({ text: "ää", at: 2 });
  });

  it("never splits a character of two UTF-16 units", () => {
    expect(fitted("abcd", "abcd😀😀", chars(5))).toEqual({ text: "abcd😀", at: 6 });
    expect(fitted("a", "a😀", inBytes(4))).toEqual({ text: "a", at: 1 });
  });

  it("lets a value that is already too long be shortened and replaced, never made longer", () => {
    const long = "x".repeat(50);
    expect(fitted(long, long.slice(1), chars(43))).toEqual({ text: long.slice(1) });
    expect(fitted(long, long + "y", chars(43))).toEqual({ text: long, at: 50 });
    expect(fitted(long, "abc" + long.slice(5), chars(43))).toEqual({ text: "abc" + long.slice(5) });
    expect(fitted(long, "abcdefg" + long.slice(5), chars(43))).toEqual({ text: "abcde" + long.slice(5), at: 5 });
  });
});

describe("templateLength", () => {
  it("counts a status template as the daemon checks it, each field it names as its widest value", () => {
    for (const { template, length } of vectors.status_templates) expect(templateLength(template), template).toBe(length);
  });

  it("holds a template to what the daemon takes for its length (what else it refuses is the daemon's to say)", () => {
    const limit = settingLimit("status/template", {});
    for (const { template, length, ok } of vectors.status_templates)
      if (length > 55 || ok) expect(limit !== undefined && limit.measure(template) <= limit.max, template).toBe(ok);
  });
});

describe("settingLimit", () => {
  it("is the comment's 43 characters, 36 with a power (the PHG extension), as the daemon's comment_limit", () => {
    expect(commentLimit({})).toBe(43);
    expect(commentLimit({ "beacon/power_w": "" })).toBe(43);
    expect(commentLimit({ "beacon/power_w": "5" })).toBe(36);
    expect(commentLimit({ "beacon/power_w": "0" })).toBe(36);
    expect(settingLimit("station/comment", { "beacon/power_w": "5" })?.max).toBe(36);
  });

  it("is the status's 55 characters, and nothing for a setting with no counter", () => {
    expect(settingLimit("station/status", {})).toMatchObject({ max: 55, kind: "characters" });
    expect(settingLimit("status/template", {})?.measure("QRV {freq} {mode}")).toBe(23);
    expect(settingLimit("station/call", {})).toBeUndefined();
    expect(settingLimit("messages/alert_command", {})).toBeUndefined();
  });
});
