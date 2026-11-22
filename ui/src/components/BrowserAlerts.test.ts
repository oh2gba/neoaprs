import { flushPromises, mount } from "@vue/test-utils";
import { effectScope } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BrowserAlerts from "@/components/BrowserAlerts.vue";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { listenForInstall } from "@/composables/useInstall";
import { APP_WINDOWS, FakeAudioContext, FakeNotification, openedAt, openedInApp, resetSeen, setSeen, stubBrowser } from "@/test/fakealert";

const scope = effectScope();

function make(host: string | null = "192.168.1.20") {
  if (host !== null) openedAt(host);
  const alerts = scope.run(() => useBrowserAlerts(vi.fn()));
  if (alerts === undefined) throw new Error("no scope");
  const say = vi.fn<(text: string) => void>();
  return { alerts, say, wrapper: mount(BrowserAlerts, { props: { alerts, say } }) };
}

const box = (wrapper: ReturnType<typeof make>["wrapper"], id: string) => wrapper.find<HTMLInputElement>(`#${id}`);

beforeEach(() => {
  localStorage.clear();
  stubBrowser();
  setSeen(false);
});
afterEach(() => {
  vi.unstubAllGlobals();
  resetSeen();
});

describe("the browser's part of the Notifications group", () => {
  it("has the Alert tickbox first, as the box of the NeoAPRS computer has, and while it is ticked Sound and Notification with their tests beside them: no dropdown", () => {
    const { wrapper } = make();
    expect(wrapper.find("fieldset.subbox > legend").text()).toBe("In this browser");
    expect(wrapper.findAll("fieldset")).toHaveLength(1);
    expect(wrapper.findAll("label").map((l) => l.text())).toEqual(["Notify me", "Sound", "Notification"]);
    expect(wrapper.findAll("select")).toHaveLength(0);
    expect(wrapper.findAll("input[type=checkbox]").map((i) => i.attributes("id"))).toEqual(["alert-mode", "alert-sound", "alert-popup"]);
    expect(wrapper.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Test sound", "Test notification"]);
    expect(wrapper.find("#alert-sound").element.nextElementSibling?.id).toBe("alert-test-sound");
    expect(wrapper.find("#alert-popup").element.nextElementSibling?.id).toBe("alert-test-popup");
    expect(wrapper.find("p").exists()).toBe(false); // (no hint sentences)
  });

  it("starts ticked, with sound and notification, for a page from another device, and unticked on the loopback", () => {
    const other = make().wrapper;
    expect([box(other, "alert-mode").element.checked, box(other, "alert-sound").element.checked, box(other, "alert-popup").element.checked]).toEqual([
      true,
      true,
      true,
    ]);
    const here = make("127.0.0.1").wrapper;
    expect(box(here, "alert-mode").element.checked).toBe(false);
    expect(here.find("#alert-sound").exists()).toBe(false);
  });

  it("keeps the old stored choice: every one of the four reads as the tickboxes show it, and Alert ticked with neither kind is the sound", () => {
    for (const [stored, shown] of [
      ["off", [false]],
      ["sound", [true, true, false]],
      ["both", [true, true, true]],
      ["popup", [true, false, true]],
    ] as const) {
      localStorage.setItem("NeoAPRS.alert.mode", stored);
      const { wrapper } = make();
      expect(
        wrapper.findAll<HTMLInputElement>("input[type=checkbox]").map((i) => i.element.checked),
        stored,
      ).toEqual(shown);
    }
  });

  it("writes what the tickboxes make as the old choice: unticking Sound leaves the notification only, unticking Alert off, and ticking it again goes back", async () => {
    const { wrapper } = make();
    await box(wrapper, "alert-sound").setValue(false);
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("popup");
    expect(box(wrapper, "alert-popup").element.disabled).toBe(true);
    await box(wrapper, "alert-sound").setValue(true);
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("both");
    await box(wrapper, "alert-popup").setValue(false);
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("sound");
    expect(box(wrapper, "alert-sound").element.disabled, "the only kind that is ticked cannot be unticked").toBe(true);
    await box(wrapper, "alert-mode").setValue(false);
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("off");
    expect(wrapper.findAll("label").map((l) => l.text())).toEqual(["Notify me"]);
    expect(wrapper.findAll("button:not(.info-toggle)")).toHaveLength(0);
    await box(wrapper, "alert-mode").setValue(true);
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("sound");
  });

  it("disables the Notification tickbox outside a secure context, with the reason on hover, and starts at the sound", () => {
    stubBrowser({ secure: false });
    const { wrapper } = make();
    expect(box(wrapper, "alert-popup").element.disabled).toBe(true);
    expect(box(wrapper, "alert-popup").attributes("title")).toBe("Notifications are off in this browser for this address");
    expect([box(wrapper, "alert-sound").element.checked, box(wrapper, "alert-popup").element.checked]).toEqual([true, false]);
  });

  it("disables it too where the browser has blocked notifications for the page", () => {
    FakeNotification.permission = "denied";
    const { wrapper } = make();
    expect(box(wrapper, "alert-popup").element.disabled).toBe(true);
    expect(box(wrapper, "alert-popup").attributes("title")).toBe("Notifications are blocked for this page in the browser");
  });

  it("asks for the permission only when the notification is ticked, and goes back to sound, saying so, when it is refused", async () => {
    FakeNotification.answer = "denied";
    const { wrapper } = make();
    localStorage.setItem("NeoAPRS.alert.mode", "sound");
    const second = make();
    await flushPromises();
    expect(FakeNotification.asked).toBe(0);
    await box(second.wrapper, "alert-popup").setValue(true);
    await flushPromises();
    expect(FakeNotification.asked).toBe(1);
    expect(box(second.wrapper, "alert-popup").element.checked).toBe(false);
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("sound");
    expect(second.wrapper.find("#alert-mode ~ [role='status']").text()).toBe("notifications refused: sound only");
    expect(wrapper.exists()).toBe(true);
  });

  it("plays the chime from Test sound and says played, not beside the button", async () => {
    const { wrapper, say } = make();
    expect(say).not.toHaveBeenCalled();
    await wrapper.find("#alert-test-sound").trigger("click");
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
    expect(say).toHaveBeenCalledExactlyOnceWith("played");
    expect(wrapper.find("#alert-test-sound ~ [role='status']").exists()).toBe(false);
  });

  it("says that the sound is locked when the browser will not let the audio run", async () => {
    FakeAudioContext.afterResume = "suspended";
    const { wrapper, say } = make();
    await wrapper.find("#alert-test-sound").trigger("click");
    await flushPromises();
    expect(say).toHaveBeenCalledExactlyOnceWith("sound locked: click the page once");
  });

  it("shows a notification from Test notification and says notification sent, not beside the button", async () => {
    FakeNotification.permission = "granted";
    const { wrapper, say } = make();
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(FakeNotification.shown).toHaveLength(1);
    expect(say).toHaveBeenCalledExactlyOnceWith("notification sent");
    expect(wrapper.find("#alert-test-popup ~ [role='status']").exists()).toBe(false);
  });

  it("says notification blocked after Test notification when the browser refuses, and why where it cannot at all", async () => {
    FakeNotification.answer = "denied";
    const { wrapper, say } = make();
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(say).toHaveBeenCalledExactlyOnceWith("notification blocked");
    stubBrowser({ secure: false });
    localStorage.setItem("NeoAPRS.alert.mode", "both");
    const insecure = make();
    await insecure.wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(insecure.say).toHaveBeenCalledExactlyOnceWith("notifications are off for this address");
  });

  it("has no Enable notifications and no steps where the page is a secure context", async () => {
    const { wrapper } = make();
    expect(wrapper.find("#alert-enable-popups").exists()).toBe(false);
    FakeNotification.permission = "granted";
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(wrapper.findAll(".linkbtn")).toHaveLength(0);
    expect(wrapper.find(".popuphelp").exists()).toBe(false);
  });

  it("offers Enable notifications… beside the Notification tickbox where the page is not a secure context, and opens the steps for the browser", async () => {
    stubBrowser({ secure: false });
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0" });
    const { wrapper } = make("neoaprs-pi.local");
    expect(wrapper.find(".popuphelp").exists()).toBe(false);
    const link = wrapper.find("#alert-popup ~ #alert-enable-popups");
    expect(link.text()).toBe("Enable notifications…");
    await link.trigger("click");
    expect(wrapper.find(".popuphelp h4").text()).toBe("Enable notifications in Firefox");
    expect(wrapper.find(".popuphelp .copyfield code").text()).toBe("neoaprs-pi.local");
    await wrapper.find(".popuphelp header button").trigger("click");
    expect(wrapper.find(".popuphelp").exists()).toBe(false);
    await link.trigger("click");
    await link.trigger("click");
    expect(wrapper.find(".popuphelp").exists()).toBe(false);
  });

  it("says in plain words after Test notification that they are off for this address", async () => {
    stubBrowser({ secure: false });
    localStorage.setItem("NeoAPRS.alert.mode", "both");
    const { wrapper, say } = make();
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    const status = say.mock.calls[0]?.[0] ?? "";
    expect(say).toHaveBeenCalledExactlyOnceWith("notifications are off for this address");
    expect(status).not.toMatch(/https|localhost|secure|context/i);
  });

  it("shows no test while Alert is unticked, the sound's alone for sound, the notification's alone for notification only, and both otherwise", async () => {
    const { wrapper } = make();
    const rows = () => wrapper.findAll("label").map((l) => l.text());
    const tests = () => wrapper.findAll("button:not(.info-toggle)").map((b) => b.text());
    expect(rows()).toEqual(["Notify me", "Sound", "Notification"]);
    await box(wrapper, "alert-mode").setValue(false);
    expect(rows()).toEqual(["Notify me"]);
    expect(tests()).toHaveLength(0);
    expect(wrapper.find("fieldset.subbox > legend").text()).toBe("In this browser");
    await box(wrapper, "alert-mode").setValue(true);
    expect(tests()).toEqual(["Test sound", "Test notification"]);
  });
});

describe("the same box in the desktop app's own window", () => {
  /** The box as the app's window shows it, in the web engine of `userAgent`. */
  const inApp = (userAgent?: string) => {
    openedInApp(userAgent);
    return make(null);
  };
  const MAC_WINDOWS = ["macOS, Qt", "macOS, WKWebView"] as const;
  const OTHER_WINDOWS = ["Linux, Qt", "Windows, WebView2", "Linux, WebKitGTK"] as const;

  it("is not there where the daemon's own alert tells, on Linux and on Windows: the window has no alert of its own", () => {
    for (const name of OTHER_WINDOWS) {
      localStorage.clear();
      stubBrowser();
      const { wrapper, alerts } = inApp(APP_WINDOWS[name]);
      expect(alerts.daemonAlone, name).toBe(true);
      expect(wrapper.find("fieldset").exists(), name).toBe(false);
      expect(wrapper.text(), name).toBe("");
    }
  });

  it("does not sound for a choice this window kept earlier, where it can no longer be switched", async () => {
    for (const stored of ["sound", "both", "popup"]) {
      localStorage.setItem("NeoAPRS.alert.mode", stored);
      stubBrowser();
      FakeNotification.permission = "granted";
      const { alerts } = inApp(APP_WINDOWS["Windows, WebView2"]);
      expect(alerts.mode.value, stored).toBe("off");
      await alerts.choose("sound");
      expect(alerts.mode.value, stored).toBe("off");
      expect(localStorage.getItem("NeoAPRS.alert.mode"), "what it kept is left as it is").toBe(stored);
    }
  });

  it("is In this window on a Mac, with the sound alone: the same rows as a browser's, the Notification row left out", async () => {
    for (const name of MAC_WINDOWS) {
      localStorage.clear();
      stubBrowser({ notifications: !name.includes("WKWebView") });
      const { wrapper } = inApp(APP_WINDOWS[name]);
      expect(wrapper.find("fieldset.subbox > legend").text(), name).toBe("In this window");
      expect(box(wrapper, "alert-mode").element.checked, name).toBe(true);
      await flushPromises();
      expect(
        wrapper.findAll("label").map((l) => l.text()),
        name,
      ).toEqual(["Notify me", "Sound"]);
      expect(
        wrapper.findAll("button:not(.info-toggle)").map((b) => b.text()),
        name,
      ).toEqual(["Test sound"]);
      expect([box(wrapper, "alert-sound").element.checked, box(wrapper, "alert-sound").element.disabled], name).toEqual([true, true]);
      expect(wrapper.find("#alert-popup").exists() || wrapper.find("#alert-enable-popups").exists(), name).toBe(false);
      expect(localStorage.getItem("NeoAPRS.alert.mode"), name).toBeNull();
      expect(FakeNotification.asked, name).toBe(0);
    }
  });

  it("offers no Install app: the window is the app", () => {
    const stop = listenForInstall();
    window.dispatchEvent(
      Object.assign(new Event("beforeinstallprompt"), { prompt: () => Promise.resolve(), userChoice: Promise.resolve({ outcome: "dismissed" }) }),
    );
    expect(make("192.168.1.20").wrapper.find("#install-app").exists()).toBe(true);
    expect(inApp(APP_WINDOWS["macOS, Qt"]).wrapper.find("#install-app").exists()).toBe(false);
    stop();
  });

  it("says window where a browser's says browser, and names no notification", async () => {
    const { wrapper } = inApp(APP_WINDOWS["macOS, Qt"]);
    await wrapper.find(".info-toggle").trigger("click");
    const tip = wrapper.find(".info-text .info-line").text();
    expect(tip).toBe("Tells you of a new message in this window, with a sound. Each device chooses for itself.");
    expect(wrapper.text()).not.toMatch(/browser|notification/i);
  });

  it("reads a kept choice with a notification without it: sound and notification is the sound, notification only is off", () => {
    for (const [stored, shown] of [
      ["off", [false]],
      ["sound", [true, true]],
      ["both", [true, true]],
      ["popup", [false]],
    ] as const) {
      localStorage.setItem("NeoAPRS.alert.mode", stored);
      const { wrapper } = inApp(APP_WINDOWS["macOS, WKWebView"]);
      expect(
        wrapper.findAll<HTMLInputElement>("input[type=checkbox]").map((i) => i.element.checked),
        stored,
      ).toEqual(shown);
      expect(wrapper.find("[role='status']").exists(), stored).toBe(false); // (no line about notifications not allowed)
    }
  });

  it("plays the chime from Test sound as a browser's does", async () => {
    localStorage.setItem("NeoAPRS.alert.mode", "sound");
    const { wrapper, say } = inApp(APP_WINDOWS["macOS, Qt"]);
    await wrapper.find("#alert-test-sound").trigger("click");
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
    expect(say).toHaveBeenCalledExactlyOnceWith("played");
  });

  it("is a browser's box again for the same computer's browser, which has no mark of the app", () => {
    inApp(APP_WINDOWS["Linux, Qt"]);
    const { wrapper } = make("127.0.0.1");
    expect(wrapper.find("fieldset.subbox > legend").text()).toBe("In this browser");
  });
});
