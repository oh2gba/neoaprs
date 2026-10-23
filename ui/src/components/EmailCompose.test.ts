import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmailCompose from "@/components/EmailCompose.vue";

function box(extra: Record<string, unknown> = {}) {
  return mount(EmailCompose, { props: { connected: true, addresses: [], ...extra } });
}
const send = (wrapper: ReturnType<typeof box>) => wrapper.find<HTMLButtonElement>("button[type='submit']");

describe("EmailCompose", () => {
  it("is the box Send an email, with To and Text", () => {
    const wrapper = box();
    expect(wrapper.find("strong").text()).toBe("Send an email");
    expect(wrapper.find("#mail-to").attributes("placeholder")).toBe("Address or shortcut");
    expect(wrapper.find("#mail-text").attributes("placeholder")).toBe("Text");
    expect(wrapper.findAll("p")).toHaveLength(0);
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
  });

  it("has Send off with no addressee, no text, a line that is too long, or the TNC not connected", async () => {
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
  });

  it("sends the addressee as typed, not in capitals, and empties the text but not the addressee", async () => {
    const wrapper = box();
    await wrapper.find("#mail-to").setValue(" jane@Example.com ");
    await wrapper.find("#mail-text").setValue("Hello");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["jane@Example.com", "Hello"]]);
    expect(wrapper.find<HTMLInputElement>("#mail-text").element.value).toBe("");
    expect(wrapper.find<HTMLInputElement>("#mail-to").element.value).toBe("jane@Example.com");
  });

  it("lists the addressees used before, and a click puts one in To", async () => {
    const wrapper = box({ addresses: ["me", "jane@example.com"] });
    expect(wrapper.findAll(".address-pick").map((b) => b.text())).toEqual(["me", "jane@example.com"]);
    await wrapper.findAll(".address-pick")[1]?.trigger("click");
    expect(wrapper.find<HTMLInputElement>("#mail-to").element.value).toBe("jane@example.com");
    expect(wrapper.emitted("send")).toBeUndefined();
  });

  it("forgets an addressee with its x, without putting it in To", async () => {
    const wrapper = box({ addresses: ["me", "jane@example.com"] });
    const x = wrapper.findAll(".address-forget");
    expect(x.map((b) => b.text())).toEqual(["", ""]);
    expect(x[0]?.attributes("title")).toBe("Forget me");
    await x[0]?.trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["me"]]);
    expect(wrapper.find<HTMLInputElement>("#mail-to").element.value).toBe("");
  });

  it("shows no list with no addressee used", () => {
    expect(box().find(".addresses").exists()).toBe(false);
  });
});
