import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Chime } from "@/lib/chime";
import { FakeAudioContext, stubBrowser } from "@/test/fakealert";

beforeEach(() => stubBrowser());
afterEach(() => vi.unstubAllGlobals());

describe("Chime", () => {
  it("is silent, and says so, until the audio is unlocked", async () => {
    const chime = new Chime();
    expect(chime.play()).toBe(false);
    expect(FakeAudioContext.made).toHaveLength(0);
    expect(await chime.unlock()).toBe(true);
    expect(chime.unlocked).toBe(true);
    expect(chime.play()).toBe(true);
    expect(FakeAudioContext.played()).toBe(2);
  });

  it("stays locked, and silent, when the browser does not let the audio run", async () => {
    FakeAudioContext.afterResume = "suspended";
    const chime = new Chime();
    expect(await chime.unlock()).toBe(false);
    expect(chime.play()).toBe(false);
    expect(FakeAudioContext.played()).toBe(0);
  });

  it("is locked for good in a browser with no Web Audio", async () => {
    vi.stubGlobal("AudioContext", undefined);
    const chime = new Chime();
    expect(await chime.unlock()).toBe(false);
    expect(chime.play()).toBe(false);
  });
});
