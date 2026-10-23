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
  vi.unstubAllGlobals();
  resetSeen();
  document.title = "NeoAPRS";
});

describe("the defaults of this browser", () => {
  it("are off for a page on the loopback, where the daemon's own alert notifies", () => {
    for (const host of ["127.0.0.1", "localhost", "[::1]"]) {
      localStorage.clear();
      openedAt(host);
      const alerts = make();
      expect(alerts.enabled.value, host).toBe(false);
    }
  });

  it("are on for a page opened from another device", () => {
    openedAt("192.168.1.20");
    const alerts = make();
    expect(alerts.enabled.value).toBe(true);
    expect(alerts.sound.value).toBe(true);
  });

  it("are what the person chose, kept in the browser", async () => {
    openedAt("192.168.1.20");
    make().enabled.value = false;
    await nextTick();
    expect(make().enabled.value).toBe(false);
    openedAt("127.0.0.1");
    localStorage.setItem("NeoAPRS.alert.web", "on");
    expect(make().enabled.value).toBe(true);
  });
});

describe("a message to us", () => {
  beforeEach(() => openedAt("192.168.1.20"));

  it("is a notification when one can be shown, and then no chime and no flash (the system has its own sound)", async () => {
    FakeNotification.permission = "granted";
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN", { text: "Moi!" })]);
    await nextTick();
    expect(FakeNotification.shown.map((n) => [n.title, n.options.body])).toEqual([["APRS message from OH2DPN", "Moi!"]]);
    expect(FakeAudioContext.played()).toBe(0);
    expect(alerts.tabTitle.value).toBeNull();
  });

  it("is the chime and the alert of the browser tab where no notification can be shown", async () => {
    stubBrowser({ secure: false });
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeNotification.shown).toEqual([]);
    expect(FakeAudioContext.played()).toBe(2);
    expect(alerts.tabTitle.value).toBe("✉ OH2DPN");
  });

  it("is the chime and the tab alert too when the permission was not given, and when the browser refuses the notification", async () => {
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeAudioContext.played()).toBe(2);
    FakeNotification.permission = "granted";
    FakeNotification.refuses = true;
    const again = make();
    await click();
    again.announce([incoming(6, "OH2DPN")]);
    expect(FakeAudioContext.played()).toBe(4);
  });

  it("falls back to the tab alone, silently, while the audio is still locked", () => {
    stubBrowser({ secure: false });
    const alerts = make();
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeAudioContext.played()).toBe(0);
    expect(alerts.tabTitle.value).toBe("✉ OH2DPN");
  });

  it("makes no sound when Sound is off, and shows nothing when the web alert is off", async () => {
    stubBrowser({ secure: false });
    const alerts = make();
    await click();
    alerts.sound.value = false;
    alerts.announce([incoming(5, "OH2DPN")]);
    expect(FakeAudioContext.played()).toBe(0);
    expect(alerts.tabTitle.value).toBe("✉ OH2DPN");
    const off = make();
    off.enabled.value = false;
    off.announce([incoming(6, "OH2PU-9")]);
    expect(off.tabTitle.value).toBeNull();
  });

  it("opens the conversation when the notification is clicked", () => {
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

  it("is one notification for each message, the same tag for the same one", () => {
    FakeNotification.permission = "granted";
    make().announce([incoming(5, "OH2DPN"), incoming(6, "OH2RDG")]);
    expect(FakeNotification.shown.map((n) => n.options.tag)).toEqual(["neoaprs-5", "neoaprs-6"]);
  });
});

describe("the Notifications switch", () => {
  beforeEach(() => openedAt("192.168.1.20"));

  it("is not possible outside a secure context, or in a browser without the API", () => {
    stubBrowser({ secure: false });
    const insecure = make();
    expect(insecure.possible).toBe(false);
    expect(insecure.notifyTitle.value).toBe("Needs https or localhost");
    vi.unstubAllGlobals();
    stubBrowser({ notifications: false });
    vi.stubGlobal("Notification", undefined);
    expect(make().possible).toBe(false);
  });

  it("never asks for the permission by itself, only when it is switched on", async () => {
    const alerts = make();
    await click();
    alerts.announce([incoming(5, "OH2DPN")]);
    await nextTick();
    expect(FakeNotification.asked).toBe(0);
    expect(alerts.notifyOn.value).toBe(false);
    await alerts.setNotify(true);
    expect(FakeNotification.asked).toBe(1);
    expect(alerts.notifyOn.value).toBe(true);
  });

  it("goes back off when the permission is refused, and is blocked once the browser says denied", async () => {
    FakeNotification.answer = "denied";
    const alerts = make();
    await alerts.setNotify(true);
    expect(alerts.notifyOn.value).toBe(false);
    expect(localStorage.getItem("NeoAPRS.alert.notify")).toBe("off");
    expect(make().notifyTitle.value).toBe("Blocked in the browser's settings");
  });

  it("is on from the start where the permission was given earlier", () => {
    FakeNotification.permission = "granted";
    expect(make().notifyOn.value).toBe(true);
    localStorage.setItem("NeoAPRS.alert.notify", "off");
    expect(make().notifyOn.value).toBe(false);
  });
});

describe("Test", () => {
  beforeEach(() => openedAt("192.168.1.20"));

  it("does what a message does: a notification where one can be shown", async () => {
    FakeNotification.permission = "granted";
    const open = vi.fn();
    const alerts = make(open);
    setSeen(true);
    await alerts.test();
    expect(FakeNotification.shown.map((n) => [n.title, n.options.body])).toEqual([["APRS message from OH2GBA-7", "This is a test of the NeoAPRS alert"]]);
    FakeNotification.shown[0]?.onclick?.();
    expect(open).not.toHaveBeenCalled(); // (there is no such conversation)
  });

  it("else plays the chime, unlocking the audio itself, and flashes the tab though the page is in front", async () => {
    const alerts = make();
    setSeen(true);
    await alerts.test();
    expect(FakeAudioContext.played()).toBe(2);
    expect(alerts.tabTitle.value).toBe("✉ OH2GBA-7");
  });
});
