import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { effectScope, nextTick } from "vue";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { FakeAudioContext, FakeNotification, openedAt, resetSeen, setSeen, stubBrowser } from "@/test/fakealert";
import { incoming } from "@/test/fixtures";

const scopes: { stop: () => void }[] = [];

function make(open: (call: string) => void = vi.fn()) {
  const scope = effectScope();
  scopes.push(scope);
  const alerts = scope.run(() => useBrowserAlerts(open));
  if (alerts === undefined) throw new Error("no scope");
  return alerts;
}

/** A click on the page: the first one unlocks the audio. */
async function click(): Promise<void> {
  window.dispatchEvent(new Event("pointerdown"));
  await Promise.resolve();
  await Promise.resolve();
}

beforeEach(() => {
  localStorage.clear();
  stubBrowser();
  setSeen(false);
});
afterEach(() => {
  scopes.splice(0).forEach((scope) => scope.stop());
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetSeen();
  document.title = "NeoAPRS";
});

describe("the default of this browser", () => {
  it("is off for a page on the loopback, where the daemon's own alert notifies", () => {
    for (const host of ["127.0.0.1", "localhost", "[::1]"]) {
      localStorage.clear();
      openedAt(host);
      expect(make().mode.value, host).toBe("off");
    }
  });

  it("is sound and pop-up for a page from another device where a pop-up is allowed", () => {
    openedAt("192.168.1.20");
    const alerts = make();
    expect(alerts.mode.value).toBe("both");
    expect(alerts.why.value).toBeUndefined();
  });

  it("is sound alone where the address does not allow a pop-up, or the browser blocked it", () => {
    openedAt("192.168.1.20");
    stubBrowser({ secure: false });
    expect(make().mode.value).toBe("sound");
    stubBrowser();
    FakeNotification.permission = "denied";
    expect(make().mode.value).toBe("sound");
  });

  it("is what the person chose, kept in the browser", async () => {
    openedAt("192.168.1.20");
    await make().choose("off");
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("off");
    expect(make().mode.value).toBe("off");
    openedAt("127.0.0.1");
    localStorage.setItem("NeoAPRS.alert.mode", "sound");
    expect(make().mode.value).toBe("sound");
  });

  it("is made from the switches of an earlier page, once", () => {
    openedAt("192.168.1.20");
    localStorage.setItem("NeoAPRS.alert.web", "on");
    localStorage.setItem("NeoAPRS.alert.sound", "off");
    localStorage.setItem("NeoAPRS.alert.notify", "on");
    expect(make().mode.value).toBe("popup");
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("popup");
    expect(localStorage.getItem("NeoAPRS.alert.web")).toBeNull();
  });
});

describe("a message to us", () => {
  beforeEach(() => openedAt("192.168.1.20"));

  it("is a pop-up when one can be shown, with the chime for sound and pop-up, and no flash of the tab", async () => {
    FakeNotification.permission = "granted";
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN", { text: "Moi!" })]);
    await nextTick();
    expect(FakeNotification.shown.map((n) => [n.title, n.options.body])).toEqual([["APRS message from OH2DPN", "Moi!"]]);
    expect(FakeAudioContext.played()).toBeGreaterThan(0);
    expect(alerts.tabTitle.value).toBeNull();
  });

  it("is a pop-up without the chime for pop-up only", async () => {
    FakeNotification.permission = "granted";
    localStorage.setItem("NeoAPRS.alert.mode", "popup");
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeNotification.shown).toHaveLength(1);
    expect(FakeAudioContext.played()).toBe(0);
  });

  it("is the chime and the alert of the browser tab, and no pop-up, for sound", async () => {
    FakeNotification.permission = "granted";
    localStorage.setItem("NeoAPRS.alert.mode", "sound");
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeNotification.shown).toEqual([]);
    expect(FakeAudioContext.played()).toBe(2);
    expect(alerts.tabTitle.value).toBe("✉ OH2DPN");
  });

  it("is nothing for off, not even the tab", async () => {
    FakeNotification.permission = "granted";
    localStorage.setItem("NeoAPRS.alert.mode", "off");
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeNotification.shown).toEqual([]);
    expect(FakeAudioContext.played()).toBe(0);
    expect(alerts.tabTitle.value).toBeNull();
  });

  it("alerts the browser tab when the browser could not show the pop-up after all", async () => {
    FakeNotification.permission = "granted";
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(alerts.tabTitle.value).toBeNull();
    FakeNotification.shown[0]?.onerror?.();
    await nextTick();
    expect(alerts.tabTitle.value).not.toBeNull();
  });

  it("is the chime and the tab alert where no pop-up can be shown, and where the permission was not given", async () => {
    stubBrowser({ secure: false });
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeNotification.shown).toEqual([]);
    expect(FakeAudioContext.played()).toBe(2);
    expect(alerts.tabTitle.value).toBe("✉ OH2DPN");
    stubBrowser();
    const asked = make();
    await click();
    asked.announce([incoming(6, "OH2DPN")]);
    expect(FakeNotification.shown).toEqual([]);
    expect(asked.tabTitle.value).toBe("✉ OH2DPN");
  });

  it("is the tab alert when the permission was taken back after the page loaded", async () => {
    FakeNotification.permission = "granted";
    const alerts = make();
    await click();
    FakeNotification.permission = "denied";
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeNotification.shown).toEqual([]);
    expect(alerts.tabTitle.value).toBe("✉ OH2DPN");
    expect(alerts.popupOn.value).toBe(false);
  });

  it("is the chime again when the browser refuses the pop-up", async () => {
    FakeNotification.permission = "granted";
    FakeNotification.refuses = true;
    const alerts = make();
    await click();
    alerts.announce([incoming(6, "OH2DPN")]);
    expect(FakeAudioContext.played()).toBe(2);
    expect(alerts.tabTitle.value).toBe("✉ OH2DPN");
  });

  it("falls back to the tab alone, silently, while the audio is still locked", () => {
    stubBrowser({ secure: false });
    const alerts = make();
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeAudioContext.played()).toBe(0);
    expect(alerts.tabTitle.value).toBe("✉ OH2DPN");
  });

  it("opens the conversation when the pop-up is clicked", () => {
    FakeNotification.permission = "granted";
    const open = vi.fn();
    const focus = vi.spyOn(window, "focus").mockImplementation(() => undefined);
    make(open).announce([incoming(5, "OH2DPN")]);
    const note = FakeNotification.shown[0];
    expect(note).toBeDefined();
    note?.onclick?.();
    expect(focus).toHaveBeenCalled();
    expect(note?.closed).toBe(true);
    expect(open).toHaveBeenCalledWith("OH2DPN");
  });

  it("is one pop-up for each message, the same tag for the same one", () => {
    FakeNotification.permission = "granted";
    make().announce([incoming(5, "OH2DPN"), incoming(6, "OH2RDG")]);
    expect(FakeNotification.shown.map((n) => n.options.tag)).toEqual(["neoaprs-5", "neoaprs-6"]);
  });
});

describe("an alert set on a station", () => {
  beforeEach(() => openedAt("192.168.1.20"));
  const fired = {
    type: "station_alert" as const,
    call: "OH2XYZ",
    kind: "within" as const,
    text: "OH2XYZ is 8.2 km from you",
    at: "2026-10-21T12:00:00Z",
    km: 8.2,
  };

  it("is a pop-up of its own, not a message's, with the chime for sound and pop-up", async () => {
    FakeNotification.permission = "granted";
    const alerts = make();
    await click();
    alerts.announceStation(fired);
    expect(FakeNotification.shown.map((n) => [n.title, n.options.body])).toEqual([["APRS alert: OH2XYZ", "OH2XYZ is 8.2 km from you"]]);
    expect(FakeAudioContext.played()).toBeGreaterThan(0);
  });

  it("flashes the browser tab with a bell, not the envelope of a message, where no pop-up is shown", async () => {
    localStorage.setItem("NeoAPRS.alert.mode", "sound");
    const alerts = make();
    await click();
    alerts.announceStation({ ...fired, kind: "on_air", km: null });
    expect(FakeNotification.shown).toEqual([]);
    expect(FakeAudioContext.played()).toBe(2);
    expect(alerts.tabTitle.value).toBe("🔔 OH2XYZ");
  });

  it("is nothing for off, as a message is", async () => {
    FakeNotification.permission = "granted";
    localStorage.setItem("NeoAPRS.alert.mode", "off");
    const alerts = make();
    await click();
    alerts.announceStation(fired);
    expect(FakeNotification.shown).toEqual([]);
    expect(FakeAudioContext.played()).toBe(0);
    expect(alerts.tabTitle.value).toBeNull();
  });
});

describe("the choice of a pop-up", () => {
  beforeEach(() => openedAt("192.168.1.20"));

  it("is impossible outside a secure context, or in a browser without the API, and says why", () => {
    stubBrowser({ secure: false });
    const insecure = make();
    expect(insecure.possible).toBe(false);
    expect(insecure.why.value).toBe("Pop-ups are off in this browser for this address");
    vi.unstubAllGlobals();
    stubBrowser({ notifications: false });
    vi.stubGlobal("Notification", undefined);
    expect(make().possible).toBe(false);
  });

  it("is impossible once the browser says denied, and says why", () => {
    FakeNotification.permission = "denied";
    expect(make().why.value).toBe("Pop-ups are blocked for this page in the browser");
  });

  it("never asks for the permission by itself, only in the click that chooses it", async () => {
    localStorage.setItem("NeoAPRS.alert.mode", "sound");
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN")]);
    await nextTick();
    expect(FakeNotification.asked).toBe(0);
    await alerts.choose("both");
    expect(FakeNotification.asked).toBe(1);
    expect(alerts.mode.value).toBe("both");
    expect(alerts.popupOn.value).toBe(true);
    expect(alerts.note.value).toBe("");
  });

  it("does not ask for the choices without a pop-up", async () => {
    const alerts = make();
    await alerts.choose("sound");
    await alerts.choose("off");
    expect(FakeNotification.asked).toBe(0);
  });

  it("does not ask again where the browser has answered", async () => {
    FakeNotification.permission = "granted";
    const alerts = make();
    await alerts.choose("popup");
    expect(FakeNotification.asked).toBe(0);
    expect(alerts.mode.value).toBe("popup");
  });

  it("falls back to sound, and says so, when the permission is refused", async () => {
    FakeNotification.answer = "denied";
    const alerts = make();
    await alerts.choose("both");
    expect(alerts.mode.value).toBe("sound");
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("sound");
    expect(alerts.note.value).toBe("pop-ups refused: sound only");
    expect(alerts.why.value).toBe("Pop-ups are blocked for this page in the browser");
    await alerts.choose("off");
    expect(alerts.note.value).toBe("");
  });

  it("says in a few words that a pop-up is chosen but not yet allowed, or blocked", () => {
    expect(make().note.value).toBe("pop-ups not allowed yet");
    FakeNotification.permission = "denied";
    localStorage.setItem("NeoAPRS.alert.mode", "popup");
    expect(make().note.value).toBe("pop-ups blocked");
    FakeNotification.permission = "granted";
    expect(make().note.value).toBe("");
  });
});

describe("Test sound", () => {
  beforeEach(() => openedAt("192.168.1.20"));

  it("plays the chime now, unlocking the audio itself, whatever the choice is, and says played for a few seconds", async () => {
    localStorage.setItem("NeoAPRS.alert.mode", "off");
    const alerts = make();
    vi.useFakeTimers();
    await alerts.testSound();
    expect(FakeAudioContext.played()).toBe(2);
    expect(alerts.soundStatus.value).toBe("played");
    expect(alerts.popupStatus.value).toBe("");
    vi.advanceTimersByTime(6000);
    expect(alerts.soundStatus.value).toBe("");
  });

  it("says the sound is locked where the browser does not let the audio run", async () => {
    FakeAudioContext.afterResume = "suspended";
    const alerts = make();
    await alerts.testSound();
    expect(FakeAudioContext.played()).toBe(0);
    expect(alerts.soundStatus.value).toBe("sound locked: click the page once");
  });

  it("neither shows a pop-up nor flashes the tab", async () => {
    FakeNotification.permission = "granted";
    const alerts = make();
    await alerts.testSound();
    expect(FakeNotification.shown).toEqual([]);
    expect(alerts.tabTitle.value).toBeNull();
  });
});

describe("Test pop-up", () => {
  beforeEach(() => openedAt("192.168.1.20"));

  it("shows a pop-up now, whatever the choice is, and says pop-up sent; a click on it opens no conversation", async () => {
    FakeNotification.permission = "granted";
    localStorage.setItem("NeoAPRS.alert.mode", "off");
    const open = vi.fn();
    const alerts = make(open);
    setSeen(true);
    await alerts.testPopup();
    expect(FakeNotification.shown.map((n) => [n.title, n.options.body])).toEqual([["APRS message from NEOAPRS", "This is a test of the NeoAPRS alert"]]);
    expect(alerts.popupStatus.value).toBe("pop-up sent");
    expect(FakeAudioContext.played()).toBe(0);
    FakeNotification.shown[0]?.onclick?.();
    expect(open).not.toHaveBeenCalled();
  });

  it("asks for the permission in its click when the browser has not been asked", async () => {
    const alerts = make();
    await alerts.testPopup();
    expect(FakeNotification.asked).toBe(1);
    expect(alerts.popupStatus.value).toBe("pop-up sent");
  });

  it("says pop-up blocked, and flashes the tab, when the permission is refused or the browser refuses", async () => {
    FakeNotification.answer = "denied";
    const refused = make();
    setSeen(true);
    await refused.testPopup();
    expect(FakeNotification.shown).toEqual([]);
    expect(refused.popupStatus.value).toBe("pop-up blocked");
    expect(refused.tabTitle.value).toBe("✉ NEOAPRS");
    FakeNotification.reset("granted");
    FakeNotification.refuses = true;
    const broken = make();
    await broken.testPopup();
    expect(broken.popupStatus.value).toBe("pop-up blocked");
  });

  it("says why where the address does not allow pop-ups", async () => {
    stubBrowser({ secure: false });
    const alerts = make();
    await alerts.testPopup();
    expect(alerts.popupStatus.value).toBe("pop-ups are off for this address");
    expect(FakeNotification.asked).toBe(0);
  });

  it("gives every test a pop-up of its own, so that a second one is not a silent replacement", async () => {
    FakeNotification.permission = "granted";
    const alerts = make();
    await alerts.testPopup();
    await new Promise((done) => setTimeout(done, 2));
    await alerts.testPopup();
    const tags = FakeNotification.shown.map((n) => n.options.tag);
    expect(tags).toHaveLength(2);
    expect(new Set(tags).size).toBe(2);
  });
});
