import { describe, expect, it } from "vitest";
import { fill, numberText, pick, placeholders, texts } from "@/i18n/message";
import { pseudoMessage, pseudoText } from "@/i18n/pseudo";

describe("fill", () => {
  it("puts the values in; a value that is not given stays, so that it is seen", () => {
    expect(fill("Update to {version}", { version: "0.6.7" }, "en")).toBe("Update to 0.6.7");
    expect(fill("{a} and {b}", { a: "x" }, "en")).toBe("x and {b}");
  });

  it("writes a number the way the language does, with no thousands separator and as many decimals as it has", () => {
    expect(fill("{n} m", { n: 12345 }, "en")).toBe("12345 m");
    expect(fill("{n}", { n: 0.5 }, "en")).toBe("0.5");
    expect(fill("{n}", { n: 0.5 }, "de")).toBe("0,5");
    expect(fill("{n}", { n: 95 }, "fr")).toBe("95");
  });

  it("has {{ and }} for a brace", () => {
    expect(fill("not a field ({{freq}})", {}, "en")).toBe("not a field ({freq})");
    expect(fill("{{{field}}} is not", { field: "x" }, "en")).toBe("{x} is not");
  });
});

describe("numberText", () => {
  it("writes the decimals asked for", () => {
    expect(numberText(1.25, "en", 1)).toBe("1.3");
    expect(numberText(3, "en", 1)).toBe("3.0");
    expect(numberText(60.17, "en", 5)).toBe("60.17000");
    expect(numberText(60.17, "fi", 5)).toBe("60,17000");
  });
});

describe("pick", () => {
  const messages = { one: "{n} message", other: "{n} messages", "=0": "no messages" };

  it("chooses the plural form of the language by n", () => {
    expect(pick(messages, { n: 1 }, "en")).toBe("{n} message");
    expect(pick(messages, { n: 3 }, "en")).toBe("{n} messages");
    expect(pick(messages, { n: 0 }, "en")).toBe("no messages");
    expect(pick({ one: "o", few: "f", many: "m", other: "x" }, { n: 3 }, "ru")).toBe("f");
    expect(pick({ one: "o", few: "f", many: "m", other: "x" }, { n: 5 }, "ru")).toBe("m");
    expect(pick({ other: "x" }, { n: 1 }, "ja")).toBe("x");
  });

  it("falls back to other when the form is not there, or n is none", () => {
    expect(pick({ other: "x" }, { n: 1 }, "en")).toBe("x");
    expect(pick(messages, {}, "en")).toBe("{n} messages");
  });

  it("chooses by the text of a value", () => {
    const choice = { select: "kind", object: "an object", other: "an item" };
    expect(pick(choice, { kind: "object" }, "en")).toBe("an object");
    expect(pick(choice, { kind: "item" }, "en")).toBe("an item");
    expect(pick(choice, {}, "en")).toBe("an item");
    expect(pick(choice, { kind: "select" }, "en")).toBe("an item");
    expect(pick({ select: "motion", "1": "moving", other: "still" }, { motion: 1 }, "en")).toBe("moving");
  });
});

describe("placeholders and texts", () => {
  it("lists the values a text asks for, not the braces", () => {
    expect(placeholders("{a} of {b}, {{c}} and {a}")).toEqual(["a", "b", "a"]);
  });

  it("lists every text of an entry", () => {
    expect(texts("x")).toEqual(["x"]);
    expect(texts({ one: "a", other: "b" })).toEqual(["a", "b"]);
    expect(texts({ select: "k", x: "a", other: "b" })).toEqual(["a", "b"]);
  });
});

describe("the pseudo-locale", () => {
  it("accents the letters, keeps the values, is a third longer and is in brackets", () => {
    const text = pseudoText("Update to {version} now");
    expect(text).toMatch(/^\[!! .*\{version\}.* !!\]$/);
    expect(text).not.toContain("Update");
    expect(text.length).toBeGreaterThan("Update to {version} now".length * 1.35);
  });

  it("keeps the form of a plural and the name of a select", () => {
    expect(pseudoMessage({ one: "{n} message", other: "{n} messages" })).toEqual({ one: pseudoText("{n} message"), other: pseudoText("{n} messages") });
    expect(pseudoMessage({ select: "kind", other: "x" })).toMatchObject({ select: "kind" });
  });
});
