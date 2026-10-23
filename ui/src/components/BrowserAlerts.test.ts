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
  return { alerts, wrapper: mount(BrowserAlerts, { props: { alerts } }) };
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
    expect(wrapper.find("h3").text()).toBe("In this browser");
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
    const why = "This address does not allow pop-ups (needs https or localhost)";
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

  it("plays the chime from Test sound and says played beside it", async () => {
    const { wrapper } = make();
    expect(wrapper.find("#alert-test-sound ~ [role='status']").exists()).toBe(false);
    await wrapper.find("#alert-test-sound").trigger("click");
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
    expect(wrapper.find("#alert-test-sound ~ [role='status']").text()).toBe("played");
  });

  it("says that the sound is locked when the browser will not let the audio run", async () => {
    FakeAudioContext.afterResume = "suspended";
    const { wrapper } = make();
    await wrapper.find("#alert-test-sound").trigger("click");
    await flushPromises();
    expect(wrapper.find("#alert-test-sound ~ [role='status']").text()).toBe("sound locked: click the page once");
  });

  it("shows a pop-up from Test pop-up and says pop-up sent beside it", async () => {
    FakeNotification.permission = "granted";
    const { wrapper } = make();
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(FakeNotification.shown).toHaveLength(1);
    expect(wrapper.find("#alert-test-popup ~ [role='status']").text()).toBe("pop-up sent");
  });

  it("says pop-up blocked beside Test pop-up when the browser refuses, and why where it cannot at all", async () => {
    FakeNotification.answer = "denied";
    const { wrapper } = make();
    await wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(wrapper.find("#alert-test-popup ~ [role='status']").text()).toBe("pop-up blocked");
    stubBrowser({ secure: false });
    const insecure = make();
    await insecure.wrapper.find("#alert-test-popup").trigger("click");
    await flushPromises();
    expect(insecure.wrapper.find("#alert-test-popup ~ [role='status']").text()).toBe("needs https or localhost");
  });

  it("has its tests enabled whatever the choice is", async () => {
    const { wrapper } = make();
    await wrapper.find("#alert-mode").setValue("off");
    expect(wrapper.findAll("button").map((b) => b.attributes("disabled"))).toEqual([undefined, undefined]);
  });
});
