import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import MessageCompose from "@/components/MessageCompose.vue";

function compose(extra: Record<string, unknown> = {}) {
  const wrapper = mount(MessageCompose, { props: { to: ["OH2RDG"], connected: true, ...extra } });
  const text = wrapper.find<HTMLInputElement>("#msg-text");
  const send = wrapper.find<HTMLButtonElement>("button[type='submit']");
  return { wrapper, text, send };
}

describe("MessageCompose", () => {
  it("is the text, 67 left and Send in one line: no To, no Stations, no list, no chips, no sentence", () => {
    const { wrapper, send } = compose();
    expect(wrapper.find("#msg-to").exists()).toBe(false);
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Send"]);
    expect(wrapper.findAll("input")).toHaveLength(1);
    expect(wrapper.find(".compose-left").text()).toBe("67 left");
    expect(wrapper.find("p").exists()).toBe(false);
    expect(send.text()).toBe("Send");
    expect([...wrapper.find(".composebar-fields").element.children].map((c) => c.tagName)).toEqual(["LABEL", "INPUT"]);
    expect([...wrapper.find(".composebar-foot").element.children].map((c) => c.tagName)).toEqual(["SPAN", "BUTTON"]);
  });

  it("sends the text to the one station as an ordinary message and empties the box", async () => {
    const { wrapper, text } = compose();
    await text.setValue("Moi Pekka");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["OH2RDG", "Moi Pekka", false]]);
    expect(wrapper.emitted("sendMany")).toBeUndefined();
    expect(text.element.value).toBe("");
  });

  it("sends on Enter in the text box", async () => {
    const { wrapper, text } = compose();
    await text.setValue("hello");
    await text.trigger("keydown.enter");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toHaveLength(1);
  });

  it("shows the bytes left of 67 as the text grows, and in red when there are too many", async () => {
    const { wrapper, text, send } = compose();
    await text.setValue("hello");
    expect(wrapper.find(".compose-left").text()).toBe("62 left");
    await text.setValue("å".repeat(34));
    expect(wrapper.find(".compose-left").text()).toBe("1 over");
    expect(wrapper.find(".compose-left").classes()).toContain("over");
    expect(send.attributes("disabled")).toBeDefined();
  });

  it("has Send off while the text is empty or the TNC is not connected, and says why in a title, not in a sentence", async () => {
    const { wrapper, text, send } = compose();
    expect(send.attributes("disabled")).toBeDefined();
    await text.setValue("hello");
    expect(send.attributes("disabled")).toBeUndefined();
    expect(send.attributes("title")).toBeUndefined();
    await wrapper.setProps({ connected: false });
    expect(send.attributes("disabled")).toBeDefined();
    expect(send.attributes("title")).toBe("The TNC is not connected");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeUndefined();
  });

  it("keeps the text in the model of the page", async () => {
    const { wrapper, text } = compose({ text: "draft" });
    expect(text.element.value).toBe("draft");
    await text.setValue("more");
    expect(wrapper.emitted("update:text")).toEqual([["more"]]);
  });
});

describe("MessageCompose to several stations", () => {
  const group = ["OH2AAA", "OH2BBB", "OH2CCC"];

  it("says Send to 3, and sends one text to all of them as a command for the page to send to each", async () => {
    const { wrapper, text, send } = compose({ to: group });
    expect(send.text()).toBe("Send to 3");
    await text.setValue("Net at 20:00");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("sendMany")).toEqual([[group, "Net at 20:00"]]);
    expect(wrapper.emitted("send")).toBeUndefined();
    expect(text.element.value).toBe("");
  });

  it("says Send for a group of one, and has Send off with nobody to send to", async () => {
    const { wrapper, text, send } = compose({ to: ["OH2AAA"] });
    expect(send.text()).toBe("Send");
    await text.setValue("Hi");
    await wrapper.setProps({ to: [] });
    expect(send.attributes("disabled")).toBeDefined();
  });
});

describe("the padlock of an encrypted message", () => {
  it("is not there unless the station can be written to that way, and then stands before Send, not pressed", () => {
    expect(compose().wrapper.find(".compose-lock").exists()).toBe(false);
    const { wrapper } = compose({ lockable: true });
    const lock = wrapper.find(".compose-lock");
    expect(lock.attributes("aria-pressed")).toBe("false");
    expect(lock.attributes("aria-label")).toBe("Encrypt");
    expect([...wrapper.find(".composebar-foot").element.children].map((c) => c.tagName)).toEqual(["SPAN", "BUTTON", "BUTTON"]);
    expect(wrapper.find(".compose-left").text()).toBe("67 left");
  });

  it("pressed, counts the 34 bytes an encrypted message holds, lets the text say ä and ö, and sends the message locked", async () => {
    const { wrapper, text, send } = compose({ lockable: true });
    await wrapper.find(".compose-lock").trigger("click");
    expect(wrapper.find(".compose-lock").attributes("aria-pressed")).toBe("true");
    expect(wrapper.find(".compose-left").text()).toBe("34 left");
    await text.setValue("Moi, täällä ok");
    expect(wrapper.find(".compose-left").text()).toBe("17 left"); // (three ä of two bytes each)
    expect(send.element.disabled).toBe(false);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toEqual([["OH2RDG", "Moi, täällä ok", true]]);
    await text.setValue("ä".repeat(18));
    expect(wrapper.find(".compose-left").text()).toBe("2 over");
    expect(send.element.disabled).toBe(true);
  });

  it("lets go when the station can no longer be written to that way", async () => {
    const { wrapper } = compose({ lockable: true });
    await wrapper.find(".compose-lock").trigger("click");
    await wrapper.setProps({ lockable: false });
    expect(wrapper.find(".compose-lock").exists()).toBe(false);
    await wrapper.setProps({ lockable: true });
    expect(wrapper.find(".compose-lock").attributes("aria-pressed")).toBe("false");
  });
});
