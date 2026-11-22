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

  it("shows the bytes left of 67 as the text grows, and takes no more: a paste is cut at the limit", async () => {
    const { wrapper, text, send } = compose();
    await text.setValue("hello");
    expect(wrapper.find(".compose-left").text()).toBe("62 left");
    await text.setValue("x".repeat(70));
    expect(text.element.value).toBe("x".repeat(67));
    expect(wrapper.find(".compose-left").text()).toBe("0 left");
    expect(wrapper.find(".compose-left").classes()).not.toContain("over");
    expect(send.attributes("disabled")).toBeUndefined();
    await text.setValue("å".repeat(34));
    expect(text.element.value).toBe("å".repeat(33)); // (two bytes each: the 34th does not fit whole)
    expect(wrapper.find(".compose-left").text()).toBe("1 left");
  });

  it("has Send off while the text is empty or the TNC is not connected, and says why in a title, not in a sentence", async () => {
    const { wrapper, text, send } = compose();
    expect(send.attributes("disabled")).toBeDefined();
    await text.setValue("hello");
    expect(send.attributes("disabled")).toBeUndefined();
    expect(send.attributes("title")).toBeUndefined();
    await wrapper.setProps({ connected: false });
    expect(send.attributes("disabled")).toBeDefined();
    expect(send.attributes("title")).toBe("The radio is not connected");
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
    expect([...wrapper.find(".composebar-foot").element.children].map((c) => c.tagName)).toEqual([
      "SPAN",
      "BUTTON",
      "BUTTON",
    ]);
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
    expect(text.element.value).toBe("ä".repeat(17));
    expect(wrapper.find(".compose-left").text()).toBe("0 left");
  });

  it("says how many bytes are over, in orange, when the padlock is pressed under a longer text, and lets it only be shortened", async () => {
    const { wrapper, text, send } = compose({ lockable: true });
    await text.setValue("x".repeat(40));
    await wrapper.find(".compose-lock").trigger("click");
    expect(wrapper.find(".compose-left").text()).toBe("6 over");
    expect(wrapper.find(".compose-left").classes()).toContain("over");
    expect(send.element.disabled).toBe(true);
    await text.setValue("x".repeat(41));
    expect(text.element.value).toBe("x".repeat(40));
    await text.setValue("x".repeat(34));
    expect(wrapper.find(".compose-left").text()).toBe("0 left");
    expect(send.element.disabled).toBe(false);
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

describe("a text the daemon would refuse", () => {
  it("keeps Send off and the text, and marks the field with the reason", async () => {
    const { wrapper, text, send } = compose();
    for (const bad of ["Hyvää päivää", "a|b", "a{b", "tilde~"]) {
      await text.setValue(bad);
      expect(send.element.disabled, bad).toBe(true);
      expect(text.classes(), bad).toContain("invalid");
      await wrapper.find("form").trigger("submit");
      expect(text.element.value).toBe(bad);
    }
    expect(text.attributes("title")).toBe("the text has ~, which a message cannot carry (| ~ { are not allowed)");
    expect(wrapper.emitted("send")).toBeUndefined();
    await text.setValue("Moi");
    expect(text.classes()).not.toContain("invalid");
    expect(text.attributes("title")).toBeUndefined();
  });

  it("lets an encrypted text say ä, since it goes sealed", async () => {
    const { wrapper, text, send } = compose({ lockable: true });
    await wrapper.find(".compose-lock").trigger("click");
    await text.setValue("Hyvää");
    expect(send.element.disabled).toBe(false);
    expect(text.classes()).not.toContain("invalid");
  });
});
