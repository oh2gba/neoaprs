import { mount } from "@vue/test-utils";
import { shown } from "@/test/shown";
import { describe, expect, it, vi } from "vitest";
import EmailCompose from "@/components/EmailCompose.vue";

function box(extra: Record<string, unknown> = {}) {
  return mount(EmailCompose, { props: { connected: true, addresses: [], ...extra }, attachTo: document.body });
}
const send = (wrapper: ReturnType<typeof box>) => wrapper.find<HTMLButtonElement>("button[type='submit']");
const picks = (wrapper: ReturnType<typeof box>) => wrapper.findAll(".suggestion-pick").map((b) => b.text());
const value = (wrapper: ReturnType<typeof box>, id: string) => wrapper.find<HTMLInputElement>(id).element.value;

describe("EmailCompose", () => {
  it("is the box to write an email in, with To, Text, the count and Send only, and no hint under it", () => {
    const wrapper = box();
    expect(wrapper.attributes("aria-label")).toBe("Write an email");
    expect(wrapper.find("fieldset > legend").text()).toBe("Write an email");
    expect(wrapper.find("label[for='mail-to']").text()).toBe("To");
    expect(wrapper.find("#mail-to").attributes("placeholder")).toBe("Email address");
    expect(wrapper.find("label[for='mail-text']").text()).toBe("Text");
    expect(wrapper.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Send"]);
    expect(send(wrapper).classes()).toContain("primary");
    expect(wrapper.findAll("p")).toHaveLength(0);
    wrapper.unmount();
  });

  it("counts the characters left of 67 over the address, the space and the text", async () => {
    const wrapper = box();
    expect(wrapper.find(".compose-left").text()).toBe("66 left");
    await wrapper.find("#mail-to").setValue("me");
    await wrapper.find("#mail-text").setValue("Hello");
    expect(wrapper.find(".compose-left").text()).toBe("59 left");
    expect(wrapper.find(".compose-left").attributes("title")).toBe("59 of 67 characters left; the address and the space count too");
    await wrapper.find("#mail-text").setValue("å".repeat(32) + "x");
    expect(wrapper.find(".compose-left").text()).toBe("1 over");
    expect(wrapper.find(".compose-left").classes()).toContain("over");
    wrapper.unmount();
  });

  it("has Send off with no address, no text, a line that is too long, or the TNC not connected", async () => {
    const wrapper = box();
    expect(send(wrapper).attributes("disabled")).toBeDefined();
    await wrapper.find("#mail-text").setValue("Hello");
    expect(send(wrapper).attributes("disabled")).toBeDefined();
    await wrapper.find("#mail-to").setValue("jane@example.com");
    expect(send(wrapper).attributes("disabled")).toBeUndefined();
    await wrapper.find("#mail-text").setValue("x".repeat(51));
    expect(send(wrapper).attributes("disabled")).toBeDefined();
    await wrapper.find("#mail-text").setValue("x".repeat(50));
    expect(send(wrapper).attributes("disabled")).toBeUndefined();
    await wrapper.setProps({ connected: false });
    expect(send(wrapper).attributes("disabled")).toBeDefined();
    expect(send(wrapper).attributes("title")).toBe("The TNC is not connected");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeUndefined();
    wrapper.unmount();
  });

  it("sends the address as typed, not in capitals, and empties the text but keeps the address, with the focus in the text", async () => {
    const wrapper = box();
    await wrapper.find("#mail-to").setValue(" jane@Example.com ");
    await wrapper.find("#mail-text").setValue("Hello");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["jane@Example.com", "Hello"]]);
    expect(value(wrapper, "#mail-text")).toBe("");
    expect(value(wrapper, "#mail-to")).toBe(" jane@Example.com ");
    expect(document.activeElement).toBe(wrapper.find("#mail-text").element);
    expect(send(wrapper).attributes("disabled")).toBeDefined();
    wrapper.unmount();
  });

  it("sends with Enter in the text, and a second mail to the same address", async () => {
    const wrapper = box();
    await wrapper.find("#mail-to").setValue("jane@example.com");
    await wrapper.find("#mail-text").setValue("One");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("#mail-text").setValue("Two");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([
      ["jane@example.com", "One"],
      ["jane@example.com", "Two"],
    ]);
    wrapper.unmount();
  });
});

describe("EmailCompose: the addresses used before", () => {
  const used = ["me", "jane@example.com", "bob@example.org"];

  it("lists them under To while it has the focus, and a click puts one in To and moves on to the text", async () => {
    const wrapper = box({ addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    expect(picks(wrapper)).toEqual(used);
    await wrapper.findAll(".suggestion-pick")[1]?.trigger("click");
    expect(value(wrapper, "#mail-to")).toBe("jane@example.com");
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    expect(document.activeElement).toBe(wrapper.find("#mail-text").element);
    expect(wrapper.emitted("send")).toBeUndefined();
    wrapper.unmount();
  });

  it("lists only the ones that match what is typed, and not the one that is typed whole", async () => {
    const wrapper = box({ addresses: used });
    await wrapper.find("#mail-to").setValue("example");
    expect(picks(wrapper)).toEqual(["jane@example.com", "bob@example.org"]);
    await wrapper.find("#mail-to").setValue("J");
    expect(picks(wrapper)).toEqual(["jane@example.com"]);
    await wrapper.find("#mail-to").setValue("ME");
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    await wrapper.find("#mail-to").setValue("nobody");
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    wrapper.unmount();
  });

  it("forgets an address with its trash can, without putting it in To", async () => {
    const wrapper = box({ addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    const x = wrapper.findAll(".suggestion .xbtn");
    expect(x.map((b) => shown(b))).toEqual(["", "", ""]);
    expect(x[0]?.attributes("title")).toBe("Forget me");
    await x[0]?.trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["me"]]);
    expect(value(wrapper, "#mail-to")).toBe("");
    wrapper.unmount();
  });

  it("closes the list on Esc and when the focus leaves, and lists nothing with no address used", async () => {
    const wrapper = box({ addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    await wrapper.find("form").trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    await wrapper.find("#mail-to").trigger("focus");
    await wrapper.find("#mail-to").trigger("focusout", { relatedTarget: document.body });
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    await wrapper.setProps({ addresses: [] });
    await wrapper.find("#mail-to").trigger("focus");
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    wrapper.unmount();
  });

  it("closes the list with the first Esc and clears the address and the text with the next, which goes no further", async () => {
    const wrapper = box({ addresses: used });
    const outside = vi.fn();
    document.addEventListener("keydown", outside);
    await wrapper.find("#mail-to").setValue("e");
    await wrapper.find("#mail-text").setValue("Hello");
    await wrapper.find("#mail-to").trigger("focus");
    expect(wrapper.find(".suggestions").exists()).toBe(true);
    await wrapper.find("form").trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    expect(value(wrapper, "#mail-to")).toBe("e");
    expect(value(wrapper, "#mail-text")).toBe("Hello");
    await wrapper.find("form").trigger("keydown", { key: "Escape" });
    expect(value(wrapper, "#mail-to")).toBe("");
    expect(value(wrapper, "#mail-text")).toBe("");
    expect(send(wrapper).attributes("disabled")).toBeDefined();
    expect(outside).not.toHaveBeenCalled();
    document.removeEventListener("keydown", outside);
    wrapper.unmount();
  });

  it("clears with the first Esc when there is nothing to suggest", async () => {
    const wrapper = box();
    await wrapper.find("#mail-to").setValue("jane@example.com");
    await wrapper.find("#mail-text").setValue("Hello");
    await wrapper.find("form").trigger("keydown", { key: "Escape" });
    expect(value(wrapper, "#mail-to")).toBe("");
    expect(value(wrapper, "#mail-text")).toBe("");
    wrapper.unmount();
  });

  it("has no contacts among the suggestions: they are addresses only", async () => {
    const wrapper = box({ addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    expect(wrapper.find(".contact-pick").exists()).toBe(false);
    expect(wrapper.find(".suggestion-hint").exists()).toBe(false);
    wrapper.unmount();
  });
});
