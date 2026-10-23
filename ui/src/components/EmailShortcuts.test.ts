import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import EmailShortcuts from "@/components/EmailShortcuts.vue";

function box(connected = true) {
  return mount(EmailShortcuts, { props: { connected } });
}
type Box = ReturnType<typeof box>;
const button = (wrapper: Box, label: string) => {
  const found = wrapper.findAll("button").find((b) => b.text() === label || (label === "Remove" && b.text() === "sure?"));
  if (found === undefined) throw new Error(`no button ${label}`);
  return found;
};
const name = (wrapper: Box, value: string) => wrapper.find("#mail-shortcut").setValue(value);
const address = (wrapper: Box, value: string) => wrapper.find("#mail-address").setValue(value);

describe("EmailShortcuts", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("has the actions named for what they do, with the command each one sends as its title", async () => {
    const wrapper = box();
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Register", "Email the list", "Remove", "Close"]);
    await name(wrapper, " john ");
    await address(wrapper, "jane@example.com");
    expect(button(wrapper, "Register").attributes("title")).toBe("Sends 'john jane@example.com': the gateway keeps the address under the name");
    expect(button(wrapper, "Email the list").attributes("title")).toBe(
      "Sends 'john L': the gateway emails the list of your shortcuts to this shortcut's address",
    );
    expect(button(wrapper, "Remove").attributes("title")).toBe("Sends 'john R': the gateway removes this shortcut");
  });

  it("asks for the shortcut where it is chosen, and the actions that need it are off until it is filled in", async () => {
    const wrapper = box();
    expect(wrapper.find("label[for='mail-shortcut']").text()).toBe("Name");
    expect(wrapper.find("#mail-shortcut").attributes("placeholder")).toBe("john");
    expect(wrapper.find("label[for='mail-address']").text()).toBe("Address");
    for (const label of ["Register", "Email the list", "Remove"]) expect(button(wrapper, label).attributes("disabled")).toBeDefined();
    expect(button(wrapper, "Email the list").attributes("title")).toContain("Fill in the shortcut's Name");
    await name(wrapper, "not a name");
    expect(button(wrapper, "Email the list").attributes("disabled")).toBeDefined();
    await name(wrapper, "john");
    expect(button(wrapper, "Email the list").attributes("disabled")).toBeUndefined();
    expect(button(wrapper, "Remove").attributes("disabled")).toBeUndefined();
    expect(button(wrapper, "Register").attributes("disabled")).toBeDefined();
    await address(wrapper, "jane");
    expect(button(wrapper, "Register").attributes("disabled")).toBeDefined();
    await address(wrapper, "jane@example.com");
    expect(button(wrapper, "Register").attributes("disabled")).toBeUndefined();
  });

  it("emails the list of a shortcut, and registers one with its address, emptying the address", async () => {
    const wrapper = box();
    await name(wrapper, "john");
    await button(wrapper, "Email the list").trigger("click");
    await address(wrapper, "jane@example.com");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("list")).toEqual([["john"]]);
    expect(wrapper.emitted("register")).toEqual([["john", "jane@example.com"]]);
    expect(wrapper.find<HTMLInputElement>("#mail-address").element.value).toBe("");
    expect(wrapper.find<HTMLInputElement>("#mail-shortcut").element.value).toBe("john");
  });

  it("removes a shortcut only after a second click, and forgets the first after 5 seconds", async () => {
    const wrapper = box();
    await name(wrapper, "john");
    await button(wrapper, "Remove").trigger("click");
    expect(button(wrapper, "Remove").text()).toBe("sure?");
    expect(button(wrapper, "Remove").classes()).toContain("danger");
    expect(wrapper.emitted("remove")).toBeUndefined();
    vi.advanceTimersByTime(5000);
    await wrapper.vm.$nextTick();
    expect(button(wrapper, "Remove").text()).toBe("Remove");
    await button(wrapper, "Remove").trigger("click");
    await button(wrapper, "Remove").trigger("click");
    expect(wrapper.emitted("remove")).toEqual([["john"]]);
    expect(button(wrapper, "Remove").text()).toBe("Remove");
  });

  it("has everything off while the TNC is not connected, and says why", async () => {
    const wrapper = box(false);
    await name(wrapper, "john");
    await address(wrapper, "jane@example.com");
    for (const label of ["Register", "Email the list", "Remove"]) {
      expect(button(wrapper, label).attributes("disabled")).toBeDefined();
      expect(button(wrapper, label).attributes("title")).toBe("The TNC is not connected");
    }
  });

  it("closes with Close and with Esc", async () => {
    const wrapper = box();
    await button(wrapper, "Close").trigger("click");
    await wrapper.find("form").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("close")).toHaveLength(2);
  });
});
