import { beforeEach, describe, expect, it } from "vitest";
import { defaultMode, modeOf, popupWhy, storedMode, wantsPopup, wantsSound } from "@/lib/alertmode";
import { readStored, writeStored } from "@/lib/storage";

beforeEach(() => localStorage.clear());

describe("the choices", () => {
  it("say which of the sound and the pop-up they have, and the tickboxes make the choice back: neither is the sound", () => {
    expect((["off", "sound", "both", "popup"] as const).map((m) => [wantsSound(m), wantsPopup(m)])).toEqual([
      [false, false],
      [true, false],
      [true, true],
      [false, true],
    ]);
    expect([modeOf(true, true), modeOf(true, false), modeOf(false, true), modeOf(false, false)]).toEqual(["both", "sound", "popup", "sound"]);
  });
});

describe("why a pop-up cannot be chosen", () => {
  it("is the address outside a secure context, or the block in the browser, else nothing", () => {
    expect(popupWhy(false, "default")).toBe("Pop-ups are off in this browser for this address");
    expect(popupWhy(true, "denied")).toBe("Pop-ups are blocked for this page in the browser");
    expect(popupWhy(true, "default")).toBeUndefined();
    expect(popupWhy(true, "granted")).toBeUndefined();
  });
});

describe("the default", () => {
  it("is off on the loopback, sound and pop-up where a pop-up is allowed, else sound", () => {
    expect(defaultMode(true, undefined)).toBe("off");
    expect(defaultMode(true, "blocked")).toBe("off");
    expect(defaultMode(false, undefined)).toBe("both");
    expect(defaultMode(false, "blocked")).toBe("sound");
  });
  it("is what storedMode gives when nothing was kept, and writes nothing", () => {
    expect(storedMode(false, undefined)).toBe("both");
    expect(storedMode(true, undefined)).toBe("off");
    expect(readStored("alert.mode")).toBeNull();
  });
});

describe("the choice that was kept", () => {
  it("is used, and a word that is none of the choices is ignored", () => {
    writeStored("alert.mode", "popup");
    expect(storedMode(false, undefined)).toBe("popup");
    writeStored("alert.mode", "loud");
    expect(storedMode(false, undefined)).toBe("both");
  });
});

describe("the migration of the three switches of an earlier page", () => {
  const keep = (web: string | null, sound: string | null, notify: string | null) => {
    localStorage.clear();
    if (web !== null) writeStored("alert.web", web);
    if (sound !== null) writeStored("alert.sound", sound);
    if (notify !== null) writeStored("alert.notify", notify);
  };

  it.each([
    ["on", "on", "on", "both"],
    ["on", "on", "off", "sound"],
    ["on", "off", "on", "popup"],
    ["on", "off", "off", "off"],
    ["off", "on", "on", "off"],
    ["on", null, null, "both"],
    ["on", null, "off", "sound"],
    [null, "off", "on", "popup"],
  ] as const)("turns web %s, sound %s, notify %s into %s (a page from another device)", (web, sound, notify, mode) => {
    keep(web, sound, notify);
    expect(storedMode(false, undefined)).toBe(mode);
  });

  it("treats a missing web alert as its default: off on the loopback, on elsewhere", () => {
    keep(null, "on", "on");
    expect(storedMode(true, undefined)).toBe("off");
    keep(null, "on", "on");
    expect(storedMode(false, undefined)).toBe("both");
  });

  it("drops the pop-up that this address cannot show", () => {
    keep("on", "on", "on");
    expect(storedMode(false, "blocked")).toBe("sound");
    keep("on", "off", "on");
    expect(storedMode(false, "blocked")).toBe("off");
  });

  it("keeps the result under the new key and removes the old ones, so that a later change is not undone by them", () => {
    keep("on", "on", "off");
    expect(storedMode(false, undefined)).toBe("sound");
    expect(readStored("alert.mode")).toBe("sound");
    expect([readStored("alert.web"), readStored("alert.sound"), readStored("alert.notify")]).toEqual([null, null, null]);
    writeStored("alert.web", "off");
    expect(storedMode(false, undefined)).toBe("sound");
  });

  it("leaves the new key alone when it is there already", () => {
    keep("off", "off", "off");
    writeStored("alert.mode", "both");
    expect(storedMode(false, undefined)).toBe("both");
  });
});
