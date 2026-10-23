import { describe, expect, it } from "vitest";
import { leftText, leftTitle, sendBlockedReason, tncNotConnected } from "@/lib/compose";

describe("leftText", () => {
  it("says what is left of a limit, and by how much it is over", () => {
    expect(leftText(67)).toBe("67 left");
    expect(leftText(0)).toBe("0 left");
    expect(leftText(-3)).toBe("3 over");
  });
});

describe("leftTitle", () => {
  it("says what is left of what, in the unit of the limit, with what else counts after it (the address of a mail, the comment of an object)", () => {
    expect(leftTitle(62, "bytes", 67)).toBe("62 of 67 bytes left");
    expect(leftTitle(-1, "characters", 67)).toBe("-1 of 67 characters left");
    expect(leftTitle(59, "address", 67)).toBe("59 of 67 characters left; the address and the space count too");
    expect(leftTitle(12, "comment")).toBe("12 characters left in the comment");
  });
});

describe("sendBlockedReason", () => {
  it("is the one sentence while the TNC is not connected, and nothing when it is", () => {
    expect(sendBlockedReason(false)).toBe(tncNotConnected());
    expect(sendBlockedReason(false)).toBe("The TNC is not connected");
    expect(sendBlockedReason(true)).toBeUndefined();
  });
});
