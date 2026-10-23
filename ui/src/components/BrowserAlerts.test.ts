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

beforeEach(() => {
  localStorage.clear();
  stubBrowser();
  setSeen(false);
});
afterEach(() => {
  vi.unstubAllGlobals();
  resetSeen();
});

describe("the group of this browser", () => {
  it("has the web alert, Sound and Notifications, each a yes or no, and a Test button", () => {
    const { wrapper } = make();
    expect(wrapper.find("legend").text()).toBe("This browser");
    expect(wrapper.findAll("label").map((l) => l.text())).toEqual(["Web alert", "Sound", "Notifications"]);
    expect(wrapper.find("button").text()).toBe("Test");
    expect(wrapper.find("p").exists()).toBe(false); // (no hint sentences)
  });

  it("is on for a page from another device and off on the loopback", () => {
    expect(make().wrapper.find<HTMLSelectElement>("#alert-web").element.value).toBe("true");
    expect(make("127.0.0.1").wrapper.find<HTMLSelectElement>("#alert-web").element.value).toBe("false");
  });

  it("keeps a change in the browser and disables the rest, and the Test, while the web alert is off", async () => {
    const { wrapper } = make();
    await wrapper.find("#alert-web").setValue("false");
    expect(localStorage.getItem("NeoAPRS.alert.web")).toBe("off");
    expect(wrapper.find("#alert-sound").attributes("disabled")).toBeDefined();
    expect(wrapper.find("#alert-notify").attributes("disabled")).toBeDefined();
    expect(wrapper.find("#alert-test").attributes("disabled")).toBeDefined();
    expect(wrapper.find("#alert-test").attributes("title")).toBe("Switch the web alert on");
  });

  it("disables Notifications outside a secure context, with the reason on hover", () => {
    stubBrowser({ secure: false });
    const { wrapper } = make();
    expect(wrapper.find("#alert-notify").attributes("disabled")).toBeDefined();
    expect(wrapper.findAll(".field")[2]?.attributes("title")).toBe("Needs https or localhost");
    expect(wrapper.find("#alert-sound").attributes("disabled")).toBeUndefined();
  });

  it("asks for the permission only from the click on the Notifications switch, and shows what came of it", async () => {
    const { wrapper } = make();
    await flushPromises();
    expect(FakeNotification.asked).toBe(0);
    const select = wrapper.find<HTMLSelectElement>("#alert-notify");
    expect(select.element.value).toBe("false");
    await select.setValue("true");
    await flushPromises();
    expect(FakeNotification.asked).toBe(1);
    expect(select.element.value).toBe("true");
  });

  it("puts the switch back to no when the permission is refused", async () => {
    FakeNotification.answer = "denied";
    const { wrapper } = make();
    const select = wrapper.find<HTMLSelectElement>("#alert-notify");
    await select.setValue("true");
    await flushPromises();
    expect(select.element.value).toBe("false");
    expect(select.attributes("disabled")).toBeDefined();
  });

  it("runs a test from the Test button", async () => {
    const { wrapper } = make();
    await wrapper.find("#alert-test").trigger("click");
    await flushPromises();
    expect(FakeAudioContext.played()).toBe(2);
  });
});
