import { describe, expect, it } from "vitest";
import { addable, canSendAll, recipientsOf } from "@/lib/recipients";

describe("recipients", () => {
  it("adds a call that is a call, is not the gateway and is not there yet", () => {
    expect(addable("oh2abc-9", [])).toBe(true);
    expect(addable("OH2ABC", ["OH2ABC"])).toBe(false);
    expect(addable("not a call", [])).toBe(false);
    for (const name of ["WINLINK", "OH2XYZ-L", "oh2xyz-20"]) expect(addable(name, []), name).toBe(true);
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
    expect(canSendAll(true, [], "WINLINK", "Hi")).toBe(true);
    expect(recipientsOf([], "oh2xyz-l")).toEqual(["OH2XYZ-L"]);
    expect(canSendAll(true, ["OH2AAA"], "oops!", "Hi")).toBe(false);
    expect(canSendAll(true, ["OH2AAA"], "EMAIL-2", "Hi")).toBe(false);
    expect(canSendAll(true, [], "", "Hi")).toBe(false);
    expect(canSendAll(true, ["OH2AAA"], "", " ")).toBe(false);
    expect(canSendAll(true, ["OH2AAA"], "", "x".repeat(68))).toBe(false);
    expect(canSendAll(false, ["OH2AAA"], "", "Hi")).toBe(false);
  });
});
