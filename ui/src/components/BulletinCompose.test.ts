import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { OwnBulletinRow } from "@/protocol/protocol";
import { ownBulletin } from "@/test/fixtures";
import BulletinCompose from "@/components/BulletinCompose.vue";

function compose() {
  const wrapper = mount(BulletinCompose, { props: { ownBulletins: new Map<string, OwnBulletinRow>() } });
  const kind = wrapper.find<HTMLSelectElement>("#post-kind");
  const id = wrapper.find<HTMLSelectElement>("#post-id");
  const text = wrapper.find<HTMLInputElement>("#post-text");
  const post = wrapper.find<HTMLButtonElement>("button[type='submit']");
  return { wrapper, kind, id, text, post };
}

describe("BulletinCompose", () => {
  it("has a kind, an identifier, the text and Post, and no sentence of help", () => {
    const { wrapper, kind, id, text, post } = compose();
    expect(kind.findAll("option").map((o) => o.text())).toEqual(["Bulletin", "Announcement", "Bulletin to a group"]);
    expect(kind.element.value).toBe("bulletin");
    expect(id.findAll("option").map((o) => o.text())).toEqual([..."0123456789"]);
    expect(id.element.value).toBe("1");
    expect(text.attributes("placeholder")).toBe("Text");
    expect(post.text()).toBe("Post");
    expect(wrapper.find("#post-group").exists()).toBe(false);
    expect(wrapper.find("p").exists()).toBe(false);
  });

  it("has an (i) that says in a few sentences what a bulletin, a bulletin to a group and a message are, closed until it is pressed", async () => {
    const { wrapper } = compose();
    const info = wrapper.find<HTMLButtonElement>(".info-toggle");
    expect(info.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find(".info-text").exists()).toBe(false);
    await info.trigger("click");
    const note = wrapper.find(".info-text").text();
    expect(note).toContain("for everyone");
    expect(note).toContain("group name");
    expect(note).toContain("Messages tab");
    await info.trigger("click");
    expect(wrapper.find(".info-text").exists()).toBe(false);
  });

  it("has Post off until there is a text that can be sent, and counts the 67 characters", async () => {
    const { wrapper, text, post } = compose();
    expect(post.element.disabled).toBe(true);
    expect(wrapper.find(".compose-left").text()).toBe("67");
    await text.setValue("Road closed");
    expect(post.element.disabled).toBe(false);
    expect(wrapper.find(".compose-left").text()).toBe("56");
    await text.setValue("x".repeat(68));
    expect(post.element.disabled).toBe(true);
    expect(wrapper.find(".compose-left").classes()).toContain("over");
    await text.setValue("a|b");
    expect(post.element.disabled).toBe(true);
  });

  it("posts the slot and the text, and keeps both until the daemon has the bulletin, then empties the text and keeps the kind and the identifier", async () => {
    const { wrapper, id, text } = compose();
    await id.setValue("3");
    await text.setValue(" Snow expected ");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLN3", "Snow expected"]]);
    expect(text.element.value).toBe(" Snow expected ");
    await wrapper.setProps({ ownBulletins: new Map([["BLN3", ownBulletin("BLN3", { text: "Snow expected" })]]) });
    expect(text.element.value).toBe("");
    expect(id.element.value).toBe("3");
  });

  it("keeps the text when the daemon refuses, and a bulletin of the slot with another text is not the answer", async () => {
    const { wrapper, text } = compose();
    await text.setValue("Road closed");
    await wrapper.find("form").trigger("submit");
    await wrapper.setProps({ ownBulletins: new Map([["BLN1", ownBulletin("BLN1", { text: "an older text" })]]) });
    expect(text.element.value).toBe("Road closed");
    await text.setValue("Road open");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([
      ["BLN1", "Road closed"],
      ["BLN1", "Road open"],
    ]);
    await wrapper.setProps({ ownBulletins: new Map([["BLN1", ownBulletin("BLN1", { text: "Road open" })]]) });
    expect(text.element.value).toBe("");
  });

  it("takes the same text posted again to a slot that holds it as done when the row is the daemon's new one, and leaves what was typed since", async () => {
    const { wrapper, text } = compose();
    const first = ownBulletin("BLN1", { text: "same" });
    await wrapper.setProps({ ownBulletins: new Map([["BLN1", first]]) });
    await text.setValue("same");
    await wrapper.find("form").trigger("submit");
    expect(text.element.value).toBe("same");
    await text.setValue("typed meanwhile");
    await wrapper.setProps({ ownBulletins: new Map([["BLN1", ownBulletin("BLN1", { text: "same", sent: 0 })]]) });
    expect(text.element.value).toBe("typed meanwhile");
  });

  it("has lettered identifiers for an announcement, and the number it had is replaced by the first letter", async () => {
    const { wrapper, kind, id, text } = compose();
    await id.setValue("7");
    await kind.setValue("announcement");
    expect(id.findAll("option")).toHaveLength(26);
    expect(id.findAll("option").map((o) => o.text())[0]).toBe("A");
    await text.setValue("Club meeting");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLNA", "Club meeting"]]);
    await id.setValue("Q");
    await text.setValue("Another");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")?.[1]).toEqual(["BLNQ", "Another"]);
    await kind.setValue("bulletin");
    await text.setValue("Back to numbers");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")?.[2]).toEqual(["BLN0", "Back to numbers"]);
  });

  it("asks for the group of a group bulletin, in capitals, one to five characters", async () => {
    const { wrapper, kind, text, post } = compose();
    await kind.setValue("group");
    const group = wrapper.find<HTMLInputElement>("#post-group");
    expect(group.exists()).toBe(true);
    expect(group.attributes("placeholder")).toBe("Group name");
    await text.setValue("Net tonight 20:00");
    expect(post.element.disabled).toBe(true);
    await group.setValue("a b");
    expect(group.classes()).toContain("invalid");
    expect(post.element.disabled).toBe(true);
    await group.setValue("hams");
    expect(group.classes()).not.toContain("invalid");
    expect(post.element.disabled).toBe(false);
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLN1HAMS", "Net tonight 20:00"]]);
    expect(group.element.value).toBe("HAMS");
  });

  it("posts nothing when Enter is pressed on a text that cannot be sent", async () => {
    const { wrapper, text } = compose();
    await text.setValue("a~b");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toBeUndefined();
  });
});
