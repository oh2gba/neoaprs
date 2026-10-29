import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import IconButton from "@/components/IconButton.vue";

describe("IconButton", () => {
  it("is a trash can titled Delete for a delete, a cross titled Close for a close, with the label for a screen reader", () => {
    const del = mount(IconButton, { props: { kind: "delete", label: "Delete the conversation with OH2RDG" } });
    expect(del.attributes("title")).toBe("Delete");
    expect(del.attributes("aria-label")).toBe("Delete the conversation with OH2RDG");
    expect(del.find("svg").exists()).toBe(true);
    expect(del.text()).toBe("");
    const close = mount(IconButton, { props: { kind: "close", label: "Close" } });
    expect(close.attributes("title")).toBe("Close");
    expect(close.find("path").attributes("d")).not.toBe(del.find("path").attributes("d"));
  });

  it("is a pin that says whether it is on: aria-pressed, the filled pin, and the title Pin card or Unpin card", async () => {
    const pin = mount(IconButton, { props: { kind: "pin", label: "Pin card" } });
    expect(pin.attributes("aria-label")).toBe("Pin card");
    expect(pin.attributes("aria-pressed")).toBe("false");
    expect(pin.attributes("title")).toBe("Pin card");
    expect(pin.classes()).not.toContain("pressed");
    expect(pin.find("path").attributes("fill")).toBe("none");
    await pin.setProps({ pressed: true });
    expect(pin.attributes("aria-pressed")).toBe("true");
    expect(pin.attributes("title")).toBe("Unpin card");
    expect(pin.classes()).toContain("pressed");
    expect(pin.find("path").attributes("fill")).toBe("currentColor");
    const other = mount(IconButton, { props: { kind: "close", label: "Close", pressed: true } });
    expect(other.attributes("aria-pressed")).toBeUndefined();
    expect(other.classes()).not.toContain("pressed");
  });

  it("has its own title when it is given one, and says sure? while it is armed", async () => {
    const wrapper = mount(IconButton, { props: { kind: "delete", label: "Delete", title: "Delete (kill on the air)" } });
    expect(wrapper.attributes("title")).toBe("Delete (kill on the air)");
    await wrapper.setProps({ armed: true });
    expect(wrapper.text()).toBe("sure?");
    expect(wrapper.classes()).toContain("armed");
    expect(wrapper.find("svg").exists()).toBe(false);
  });

  it("is a plain button, not one that submits a form, and a click on it is the parent's", async () => {
    let clicks = 0;
    const wrapper = mount(IconButton, { props: { kind: "close", label: "Close" }, attrs: { onClick: () => clicks++ } });
    expect(wrapper.attributes("type")).toBe("button");
    await wrapper.trigger("click");
    expect(clicks).toBe(1);
  });
});
