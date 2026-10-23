import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import EmailMailbox from "@/components/EmailMailbox.vue";

function box(connected = true, own: [string, number][] = []) {
  return mount(EmailMailbox, { props: { connected, attempts: { own: new Map(own), defaultCount: 6 } } });
}
type Box = ReturnType<typeof box>;
const button = (wrapper: Box, label: string) => {
  const found = wrapper.findAll("button").find((b) => b.text() === label || (label === "Remove" && b.text() === "sure?"));
  if (found === undefined) throw new Error(`no button ${label}`);
  return found;
};
const name = (wrapper: Box, value: string) => wrapper.find("#mail-shortcut").setValue(value);
const address = (wrapper: Box, value: string) => wrapper.find("#mail-address").setValue(value);

describe("EmailMailbox", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("has the actions named for what they do, with the command each one sends as its title", async () => {
    const wrapper = box();
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Fetch held mail", "Register", "Email the list", "Remove"]);
    expect(wrapper.findAll("strong").map((s) => s.text())).toEqual(["Mailbox", "Shortcuts"]);
    expect(button(wrapper, "Fetch held mail").attributes("title")).toBe("Sends 'get': the gateway sends again the mail it holds for you");
    await name(wrapper, " john ");
    await address(wrapper, "jane@example.com");
    expect(button(wrapper, "Register").attributes("title")).toBe("Sends 'john jane@example.com': the gateway keeps the address under the name");
    expect(button(wrapper, "Email the list").attributes("title")).toBe(
      "Sends 'john L': the gateway emails the list of your shortcuts to this shortcut's address",
    );
    expect(button(wrapper, "Remove").attributes("title")).toBe("Sends 'john R': the gateway removes this shortcut");
  });

  it("asks for the shortcut where it is chosen: a label and a placeholder, and the actions that need it are off until it is filled in", async () => {
    const wrapper = box();
    expect(wrapper.find("label[for='mail-shortcut']").text()).toBe("Your shortcut");
    expect(wrapper.find("#mail-shortcut").attributes("placeholder")).toBe("a name for the gateway");
    expect(wrapper.find("label[for='mail-address']").text()).toBe("Its address");
    for (const label of ["Register", "Email the list", "Remove"]) expect(button(wrapper, label).attributes("disabled")).toBeDefined();
    expect(button(wrapper, "Email the list").attributes("title")).toContain("Fill in Your shortcut");
    expect(button(wrapper, "Fetch held mail").attributes("disabled")).toBeUndefined();
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

  it("fetches the held mail, emails the list of a shortcut, and registers one with its address", async () => {
    const wrapper = box();
    await button(wrapper, "Fetch held mail").trigger("click");
    await name(wrapper, "john");
    await button(wrapper, "Email the list").trigger("click");
    await address(wrapper, " jane@example.com ");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("get")).toHaveLength(1);
    expect(wrapper.emitted("list")).toEqual([["john"]]);
    expect(wrapper.emitted("register")).toEqual([["john", "jane@example.com"]]);
    expect(wrapper.find<HTMLInputElement>("#mail-address").element.value).toBe("");
    expect(wrapper.find<HTMLInputElement>("#mail-shortcut").element.value).toBe("john");
  });

  it("registers nothing without an address, from the Enter key too", async () => {
    const wrapper = box();
    await name(wrapper, "john");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("register")).toBeUndefined();
  });

  it("asks twice before removing: the button says sure?, the first press is forgotten after 5 seconds, and nothing else asks", async () => {
    const wrapper = box();
    await name(wrapper, "john");
    await button(wrapper, "Remove").trigger("click");
    expect(wrapper.emitted("remove")).toBeUndefined();
    expect(button(wrapper, "Remove").text()).toBe("sure?");
    expect(button(wrapper, "Remove").classes()).toContain("danger");
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Fetch held mail", "Register", "Email the list", "sure?"]);
    await vi.advanceTimersByTimeAsync(5100);
    expect(button(wrapper, "Remove").text()).toBe("Remove");
    await button(wrapper, "Remove").trigger("click");
    await name(wrapper, "jane");
    expect(button(wrapper, "Remove").text()).toBe("Remove");
    await button(wrapper, "Remove").trigger("click");
    await button(wrapper, "Remove").trigger("click");
    expect(wrapper.emitted("remove")).toEqual([["jane"]]);
    expect(button(wrapper, "Remove").text()).toBe("Remove");
  });

  it("has the gateway's attempts in the Mailbox row: the setting as the placeholder, saved when changed, cleared by the x", async () => {
    const wrapper = box();
    expect(wrapper.find(".mail-row .attempts-input").attributes("placeholder")).toBe("(default: 6)");
    expect(wrapper.find(".use-default").exists()).toBe(false);
    await wrapper.find(".attempts-input").setValue("2");
    expect(wrapper.emitted("setAttempts")).toEqual([["EMAIL-2", 2]]);
    const own = box(true, [["EMAIL-2", 2]]);
    expect(own.find<HTMLInputElement>(".attempts-input").element.value).toBe("2");
    await own.find(".attemptsbox .use-default").trigger("click");
    expect(own.emitted("clearAttempts")).toEqual([["EMAIL-2"]]);
  });

  it("is off, with the title, while the TNC is not connected", async () => {
    const wrapper = box(false);
    await name(wrapper, "john");
    await address(wrapper, "jane@example.com");
    for (const b of wrapper.findAll("button")) {
      expect(b.attributes("disabled")).toBeDefined();
      expect(b.attributes("title")).toBe("The TNC is not connected");
    }
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("register")).toBeUndefined();
  });
});
