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

const options = (wrapper: ReturnType<typeof make>["wrapper"]) =>
  wrapper.findAll("#alert-mode option").map((o) => ({ label: o.text(), disabled: o.attributes("disabled") !== undefined, title: o.attributes("title") }));

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
  it("has one choice, Alert for a new message, and a test for the sound and one for the pop-up", () => {
    const { wrapper } = make();
    expect(wrapper.find("fieldset.subbox > legend").text()).toBe("In this browser");
    expect(wrapper.find("h3").exists()).toBe(false);
    expect(wrapper.findAll("fieldset")).toHaveLength(1);
    expect(wrapper.findAll("label").map((l) => l.text())).toEqual(["Alert for a new message", "Sound", "Pop-up"]);
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Test sound", "Test pop-up"]);
    expect(wrapper.findAll("select")).toHaveLength(1);
    expect(wrapper.find("p").exists()).toBe(false); // (no hint sentences)
  });

  it("offers off, sound, sound and pop-up, and pop-up only, all enabled where a pop-up is allowed", () => {
    expect(options(make().wrapper)).toEqual([
      { label: "off", disabled: false, title: undefined },
      { label: "sound", disabled: false, title: undefined },
      { label: "sound and pop-up", disabled: false, title: undefined },
      { label: "pop-up only", disabled: false, title: undefined },
    ]);
  });

  it("starts at sound and pop-up for a page from another device, and at off on the loopback", () => {
    expect(make().wrapper.find<HTMLSelectElement>("#alert-mode").element.value).toBe("both");
    expect(make("127.0.0.1").wrapper.find<HTMLSelectElement>("#alert-mode").element.value).toBe("off");
  });

  it("disables the choices with a pop-up outside a secure context, each with the reason on hover", () => {
    stubBrowser({ secure: false });
    const { wrapper } = make();
    const why = "Pop-ups are off in this browser for this address";
    expect(options(wrapper)).toEqual([
      { label: "off", disabled: false, title: undefined },
      { label: "sound", disabled: false, title: undefined },
      { label: "sound and pop-up", disabled: true, title: why },
      { label: "pop-up only", disabled: true, title: why },
    ]);
    expect(wrapper.find<HTMLSelectElement>("#alert-mode").element.value).toBe("sound");
  });

  it("disables them too where the browser has blocked pop-ups for the page", () => {
    FakeNotification.permission = "denied";
    const { wrapper } = make();
    expect(options(wrapper).map((o) => [o.disabled, o.title])).toEqual([
      [false, undefined],
      [false, undefined],
      [true, "Pop-ups are blocked for this page in the browser"],
      [true, "Pop-ups are blocked for this page in the browser"],
    ]);
  });

  it("keeps a change in the browser, and asks for the permission only when a pop-up is chosen", async () => {
    const { wrapper } = make();
    await flushPromises();
    expect(FakeNotification.asked).toBe(0);
    const select = wrapper.find<HTMLSelectElement>("#alert-mode");
    await select.setValue("sound");
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("sound");
    expect(FakeNotification.asked).toBe(0);
    await select.setValue("popup");
    await flushPromises();
    expect(FakeNotification.asked).toBe(1);
    expect(select.element.value).toBe("popup");
    expect(localStorage.getItem("NeoAPRS.alert.mode")).toBe("popup");
  });

  it("goes back to sound, and says so next to the choice, when the permission is refused", async () => {
    FakeNotification.answer = "denied";
    const { wrapper } = make();
    const select = wrapper.find<HTMLSelectElement>("#alert-mode");
    await select.setValue("popup");
    await flushPromises();
    expect(select.element.value).toBe("sound");
    expect(wrapper.find("#alert-mode ~ [role='status']").text()).toBe("pop-ups refused: sound only");
    expect(options(wrapper)[2]?.disabled).toBe(true);
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

  it("offers Enable pop-ups… beside the choice where the page is not a secure context, and opens the steps for the browser", async () => {
    stubBrowser({ secure: false });
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0" });
    const { wrapper } = make("neoaprs-pi.local");
    expect(wrapper.find(".popuphelp").exists()).toBe(false);
    const link = wrapper.find("#alert-mode ~ #alert-enable-popups");
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

  it("says in plain words after Test pop-up that they are off for this address, and offers the same link", async () => {
    stubBrowser({ secure: false });
    const { wrapper, say } = make();
    expect(wrapper.find("#alert-test-popup ~ .linkbtn").exists()).toBe(false);
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    const status = say.mock.calls[0]?.[0] ?? "";
    expect(say).toHaveBeenCalledExactlyOnceWith("pop-ups are off for this address");
    expect(status).not.toMatch(/https|localhost|secure|context/i);
    await wrapper.find("#alert-test-popup ~ .linkbtn").trigger("click");
    expect(wrapper.find(".popuphelp").exists()).toBe(true);
  });

  it("has its tests enabled whatever the choice is", async () => {
    const { wrapper } = make();
    await wrapper.find("#alert-mode").setValue("off");
    expect(wrapper.findAll("button").map((b) => b.attributes("disabled"))).toEqual([undefined, undefined]);
  });
});
