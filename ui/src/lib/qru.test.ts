import { describe, expect, it } from "vitest";
import { kmOf, kmWrong, requestText } from "@/lib/qru";
import { LIMITS } from "@/protocol/lists";

describe("the distance of a request for local info", () => {
  it("is empty, or a whole number of km from 1 to the most the daemon takes", () => {
    expect(kmOf("")).toBeNull();
    expect(kmOf("  ")).toBeNull();
    expect(kmOf(" 150 ")).toBe(150);
    expect(kmOf("1")).toBe(1);
    expect(kmOf(String(LIMITS.qru.kmMax))).toBe(LIMITS.qru.kmMax);
    for (const wrong of ["0", String(LIMITS.qru.kmMax + 1), "-5", "1.5", "5 km", "x", "100000"]) expect(kmWrong(wrong), wrong).toBe(true);
    expect(kmWrong("")).toBe(false);
  });

  it("goes after the word in the text of the request, none for a wrong one", () => {
    expect(requestText("INFO", "")).toBe("INFO");
    expect(requestText("RP70", "20")).toBe("RP70 20");
    expect(requestText("RP70", "0")).toBeNull();
  });
});
