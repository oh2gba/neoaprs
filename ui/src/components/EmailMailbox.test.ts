import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmailMailbox from "@/components/EmailMailbox.vue";

function box(connected = true) {
  return mount(EmailMailbox, { props: { connected }, attachTo: document.body });
}
const items = (wrapper: ReturnType<typeof box>) => wrapper.findAll("[role='menuitem']");

describe("EmailMailbox", () => {
  it("is one button, Mailbox, with the menu closed", () => {
    const wrapper = box();
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Mailbox"]);
    expect(wrapper.find("button").attributes("aria-expanded")).toBe("false");
    expect(items(wrapper)).toHaveLength(0);
    wrapper.unmount();
  });

  it("opens with Fetch held mail and Shortcuts…, the command as the title", async () => {
    const wrapper = box();
    await wrapper.find("button").trigger("click");
    expect(wrapper.find("button").attributes("aria-expanded")).toBe("true");
    expect(items(wrapper).map((b) => b.text())).toEqual(["Fetch held mail", "Shortcuts…"]);
    expect(items(wrapper)[0]?.attributes("title")).toBe("Sends 'get': the gateway sends again the mail it holds for you");
    wrapper.unmount();
  });

  it("fetches the held mail and closes", async () => {
    const wrapper = box();
    await wrapper.find("button").trigger("click");
    await items(wrapper)[0]?.trigger("click");
    expect(wrapper.emitted("get")).toEqual([[]]);
    expect(items(wrapper)).toHaveLength(0);
    wrapper.unmount();
  });

  it("asks the tab for the shortcuts and closes", async () => {
    const wrapper = box();
    await wrapper.find("button").trigger("click");
    await items(wrapper)[1]?.trigger("click");
    expect(wrapper.emitted("shortcuts")).toEqual([[]]);
    expect(wrapper.emitted("get")).toBeUndefined();
    expect(items(wrapper)).toHaveLength(0);
    wrapper.unmount();
  });

  it("has Fetch held mail off while the TNC is not connected, and says why", async () => {
    const wrapper = box(false);
    await wrapper.find("button").trigger("click");
    expect(items(wrapper)[0]?.attributes("disabled")).toBeDefined();
    expect(items(wrapper)[0]?.attributes("title")).toBe("The TNC is not connected");
    expect(items(wrapper)[1]?.attributes("disabled")).toBeUndefined();
    wrapper.unmount();
  });

  it("closes with Esc and with a click outside", async () => {
    const wrapper = box();
    await wrapper.find("button").trigger("click");
    await wrapper.find(".mail-menu").trigger("keydown", { key: "Escape" });
    expect(items(wrapper)).toHaveLength(0);
    await wrapper.find("button").trigger("click");
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(items(wrapper)).toHaveLength(0);
    wrapper.unmount();
  });
});
