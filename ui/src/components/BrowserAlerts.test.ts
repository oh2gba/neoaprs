import { flushPromises, mount } from "@vue/test-utils";
import { effectScope } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BrowserAlerts from "@/components/BrowserAlerts.vue";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { FakeAudioContext, FakeNotification, openedAt, resetSeen, setSeen, stubBrowser } from "@/test/fakealert";

const scope = effectScope();

function make(host = "192.168.1.20") {
  openedAt(host);
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
  it("has the Alert tickbox first, as the box of the NeoAPRS computer has, and while it is ticked Sound and Pop-up with their tests beside them: no dropdown", () => {
    const { wrapper } = make();
    expect(wrapper.find("fieldset.subbox > legend").text()).toBe("In this browser");
    expect(wrapper.findAll("fieldset")).toHaveLength(1);
    expect(wrapper.findAll("label").map((l) => l.text())).toEqual(["Alert", "Sound", "Pop-up"]);
    expect(wrapper.findAll("select")).toHaveLength(0);
    expect(wrapper.findAll("input[type=checkbox]").map((i) => i.attributes("id"))).toEqual(["alert-mode", "alert-sound", "alert-popup"]);
    expect(wrapper.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Test sound", "Test pop-up"]);
    expect(wrapper.find("#alert-sound").element.nextElementSibling?.id).toBe("alert-test-sound");
    expect(wrapper.find("#alert-popup").element.nextElementSibling?.id).toBe("alert-test-popup");
    expect(wrapper.find("p").exists()).toBe(false); // (no hint sentences)
  });

  it("starts ticked, with sound and pop-up, for a page from another device, and unticked on the loopback", () => {
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

  it("writes what the tickboxes make as the old choice: unticking Sound leaves the pop-up only, unticking Alert off, and ticking it again goes back", async () => {
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
    expect(wrapper.findAll("label").map((l) => l.text())).toEqual(["Alert"]);
    expect(wrapper.findAll("button:not(.info-toggle)")).toHaveLength(0);
    await box(wrapper, "alert-mode").setValue(true);
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("sound");
  });

  it("disables the Pop-up tickbox outside a secure context, with the reason on hover, and starts at the sound", () => {
    stubBrowser({ secure: false });
    const { wrapper } = make();
    expect(box(wrapper, "alert-popup").element.disabled).toBe(true);
    expect(box(wrapper, "alert-popup").attributes("title")).toBe("Pop-ups are off in this browser for this address");
    expect([box(wrapper, "alert-sound").element.checked, box(wrapper, "alert-popup").element.checked]).toEqual([true, false]);
  });

  it("disables it too where the browser has blocked pop-ups for the page", () => {
    FakeNotification.permission = "denied";
    const { wrapper } = make();
    expect(box(wrapper, "alert-popup").element.disabled).toBe(true);
    expect(box(wrapper, "alert-popup").attributes("title")).toBe("Pop-ups are blocked for this page in the browser");
  });

  it("asks for the permission only when the pop-up is ticked, and goes back to sound, saying so, when it is refused", async () => {
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
    expect(second.wrapper.find("#alert-mode ~ [role='status']").text()).toBe("pop-ups refused: sound only");
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

  it("shows a pop-up from Test pop-up and says pop-up sent, not beside the button", async () => {
    FakeNotification.permission = "granted";
    const { wrapper, say } = make();
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(FakeNotification.shown).toHaveLength(1);
    expect(say).toHaveBeenCalledExactlyOnceWith("pop-up sent");
    expect(wrapper.find("#alert-test-popup ~ [role='status']").exists()).toBe(false);
  });

  it("says pop-up blocked after Test pop-up when the browser refuses, and why where it cannot at all", async () => {
    FakeNotification.answer = "denied";
    const { wrapper, say } = make();
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(say).toHaveBeenCalledExactlyOnceWith("pop-up blocked");
    stubBrowser({ secure: false });
    localStorage.setItem("NeoAPRS.alert.mode", "both");
    const insecure = make();
    await insecure.wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(insecure.say).toHaveBeenCalledExactlyOnceWith("pop-ups are off for this address");
  });

  it("has no Enable pop-ups and no steps where the page is a secure context", async () => {
    const { wrapper } = make();
    expect(wrapper.find("#alert-enable-popups").exists()).toBe(false);
    FakeNotification.permission = "granted";
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(wrapper.findAll(".linkbtn")).toHaveLength(0);
    expect(wrapper.find(".popuphelp").exists()).toBe(false);
  });

  it("offers Enable pop-ups… beside the Pop-up tickbox where the page is not a secure context, and opens the steps for the browser", async () => {
    stubBrowser({ secure: false });
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0" });
    const { wrapper } = make("neoaprs-pi.local");
    expect(wrapper.find(".popuphelp").exists()).toBe(false);
    const link = wrapper.find("#alert-popup ~ #alert-enable-popups");
    expect(link.text()).toBe("Enable pop-ups…");
    await link.trigger("click");
    expect(wrapper.find(".popuphelp h4").text()).toBe("Enable pop-ups in Firefox");
    expect(wrapper.find(".popuphelp .copyfield code").text()).toBe("neoaprs-pi.local");
    await wrapper.find(".popuphelp header button").trigger("click");
    expect(wrapper.find(".popuphelp").exists()).toBe(false);
    await link.trigger("click");
    await link.trigger("click");
    expect(wrapper.find(".popuphelp").exists()).toBe(false);
  });

  it("says in plain words after Test pop-up that they are off for this address", async () => {
    stubBrowser({ secure: false });
    localStorage.setItem("NeoAPRS.alert.mode", "both");
    const { wrapper, say } = make();
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    const status = say.mock.calls[0]?.[0] ?? "";
    expect(say).toHaveBeenCalledExactlyOnceWith("pop-ups are off for this address");
    expect(status).not.toMatch(/https|localhost|secure|context/i);
  });

  it("shows no test while Alert is unticked, the sound's alone for sound, the pop-up's alone for pop-up only, and both otherwise", async () => {
    const { wrapper } = make();
    const rows = () => wrapper.findAll("label").map((l) => l.text());
    const tests = () => wrapper.findAll("button:not(.info-toggle)").map((b) => b.text());
    expect(rows()).toEqual(["Alert", "Sound", "Pop-up"]);
    await box(wrapper, "alert-mode").setValue(false);
    expect(rows()).toEqual(["Alert"]);
    expect(tests()).toHaveLength(0);
    expect(wrapper.find("fieldset.subbox > legend").text()).toBe("In this browser");
    await box(wrapper, "alert-mode").setValue(true);
    expect(tests()).toEqual(["Test sound", "Test pop-up"]);
  });
});
