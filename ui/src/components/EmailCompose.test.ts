import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import EmailCompose from "@/components/EmailCompose.vue";

function box(extra: Record<string, unknown> = {}) {
  return mount(EmailCompose, { props: { connected: true, addresses: [], ...extra }, attachTo: document.body });
}
const send = (wrapper: ReturnType<typeof box>) => wrapper.find<HTMLButtonElement>("button[type='submit']");
const picks = (wrapper: ReturnType<typeof box>) => wrapper.findAll(".suggestion-pick").map((b) => b.text());

describe("EmailCompose", () => {
  it("is the form New email, with To, Text, the count and Cancel and Send, and the focus in To", () => {
    const wrapper = box();
    expect(wrapper.attributes("aria-label")).toBe("New email");
    expect(wrapper.find("label[for='mail-to']").text()).toBe("To");
    expect(wrapper.find("#mail-to").attributes("placeholder")).toBe("Name or address");
    expect(wrapper.find("#mail-text").attributes("placeholder")).toBe("Text");
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Cancel", "Send"]);
    expect(wrapper.findAll("p")).toHaveLength(0);
    expect(document.activeElement).toBe(wrapper.find("#mail-to").element);
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
    wrapper.unmount();
  });

  it("sends the addressee as typed, not in capitals", async () => {
    const wrapper = box();
    await wrapper.find("#mail-to").setValue(" jane@Example.com ");
    await wrapper.find("#mail-text").setValue("Hello");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["jane@Example.com", "Hello"]]);
    wrapper.unmount();
  });

  it("cancels with Cancel and with Esc", async () => {
    const wrapper = box();
    await wrapper.findAll("button")[0]?.trigger("click");
    await wrapper.find("form").trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("cancel")).toHaveLength(2);
    wrapper.unmount();
  });
});

describe("EmailCompose: the addressees used before", () => {
  const used = ["me", "jane@example.com", "bob@example.org"];

  it("lists them under To while it has the focus, and a click puts one in To and moves on to the text", async () => {
    const wrapper = box({ addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    expect(picks(wrapper)).toEqual(used);
    await wrapper.findAll(".suggestion-pick")[1]?.trigger("click");
    expect(wrapper.find<HTMLInputElement>("#mail-to").element.value).toBe("jane@example.com");
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

  it("forgets an addressee with its trash can, without putting it in To", async () => {
    const wrapper = box({ addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    const x = wrapper.findAll(".suggestion .xbtn");
    expect(x.map((b) => b.text())).toEqual(["", "", ""]);
    expect(x[0]?.attributes("title")).toBe("Forget me");
    await x[0]?.trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["me"]]);
    expect(wrapper.find<HTMLInputElement>("#mail-to").element.value).toBe("");
    wrapper.unmount();
  });

  it("closes the list on Esc (the form stays) and when the focus leaves, and lists nothing with no addressee used", async () => {
    const wrapper = box({ addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    await wrapper.find("form").trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    expect(wrapper.emitted("cancel")).toBeUndefined();
    await wrapper.find("#mail-to").trigger("focus");
    await wrapper.find("#mail-to").trigger("focusout", { relatedTarget: document.body });
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    await wrapper.setProps({ addresses: [] });
    await wrapper.find("#mail-to").trigger("focus");
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    wrapper.unmount();
  });
});

describe("EmailCompose: the contacts", () => {
  const contacts = [
    { name: "me", address: "jane@example.com", state: "confirmed" as const },
    { name: "Bob", address: "bob@example.org", state: "unconfirmed" as const },
  ];
  const used = ["bob", "carl@example.net", "jane@example.com"];

  it("lists the contacts first, each with its address, then the addressees used before without the names of contacts", async () => {
    const wrapper = box({ contacts, addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    expect(wrapper.findAll(".contact-pick").map((li) => [li.find(".mono").text(), li.find(".suggestion-hint").text()])).toEqual([
      ["me", "jane@example.com"],
      ["Bob", "bob@example.org"],
    ]);
    expect(wrapper.findAll(".suggestion").map((li) => li.classes().includes("contact-pick"))).toEqual([true, true, false, false]);
    expect(wrapper.findAll(".suggestion:not(.contact-pick) .suggestion-pick").map((b) => b.text())).toEqual(["carl@example.net", "jane@example.com"]);
    wrapper.unmount();
  });

  it("has no trash can on a contact (Remove in Contacts does that), and one on an address used before", async () => {
    const wrapper = box({ contacts, addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    expect(wrapper.findAll(".contact-pick .xbtn")).toHaveLength(0);
    expect(wrapper.findAll(".suggestion:not(.contact-pick) .xbtn")).toHaveLength(2);
    wrapper.unmount();
  });

  it("lists the contacts that match what is typed, by name or by address, and not the one whose name is typed whole", async () => {
    const wrapper = box({ contacts, addresses: used });
    await wrapper.find("#mail-to").setValue("bob@");
    expect(wrapper.findAll(".contact-pick .mono:first-child").map((b) => b.text())).toEqual(["Bob"]);
    await wrapper.find("#mail-to").setValue("JANE");
    expect(wrapper.findAll(".contact-pick .mono:first-child").map((b) => b.text())).toEqual(["me"]);
    await wrapper.find("#mail-to").setValue("ME");
    expect(wrapper.find(".contact-pick").exists()).toBe(false);
    wrapper.unmount();
  });

  it("puts the name of the contact in To when it is picked, and moves on to the text", async () => {
    const wrapper = box({ contacts, addresses: used });
    await wrapper.find("#mail-to").trigger("focus");
    await wrapper.find(".contact-pick .suggestion-pick").trigger("click");
    expect(wrapper.find<HTMLInputElement>("#mail-to").element.value).toBe("me");
    expect(document.activeElement).toBe(wrapper.find("#mail-text").element);
    wrapper.unmount();
  });

  it("opens with the name given by a contact's Mail button in To, and the focus in the text", () => {
    const wrapper = box({ contacts, addresses: used, to: "me" });
    expect(wrapper.find<HTMLInputElement>("#mail-to").element.value).toBe("me");
    expect(document.activeElement).toBe(wrapper.find("#mail-text").element);
    expect(wrapper.find(".suggestions").exists()).toBe(false);
    wrapper.unmount();
  });
});
