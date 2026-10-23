import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BulletinCompose from "@/components/BulletinCompose.vue";

function compose() {
  const wrapper = mount(BulletinCompose);
  const kind = wrapper.find<HTMLSelectElement>("#post-kind");
  const id = wrapper.find<HTMLSelectElement>("#post-id");
  const text = wrapper.find<HTMLInputElement>("#post-text");
  const post = wrapper.find<HTMLButtonElement>("button[type='submit']");
  return { wrapper, kind, id, text, post };
}

describe("BulletinCompose", () => {
  it("has a kind, an identifier, the text and Post, and no sentence of help", () => {
    const { wrapper, kind, id, text, post } = compose();
    expect(kind.findAll("option").map((o) => o.text())).toEqual(["Bulletin", "Announcement", "Group"]);
    expect(kind.element.value).toBe("bulletin");
    expect(id.findAll("option").map((o) => o.text())).toEqual([..."0123456789"]);
    expect(id.element.value).toBe("1");
    expect(text.attributes("placeholder")).toBe("Text");
    expect(post.text()).toBe("Post");
    expect(wrapper.find("#post-group").exists()).toBe(false);
    expect(wrapper.find("p").exists()).toBe(false);
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

  it("posts the slot and the text, and empties the text but keeps the kind and the identifier", async () => {
    const { wrapper, id, text } = compose();
    await id.setValue("3");
    await text.setValue(" Snow expected ");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("post")).toEqual([["BLN3", "Snow expected"]]);
    expect(text.element.value).toBe("");
    expect(id.element.value).toBe("3");
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
    expect(group.attributes("placeholder")).toBe("Group");
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
