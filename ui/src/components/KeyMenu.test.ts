import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import KeyMenu from "@/components/KeyMenu.vue";

const theirs = { fingerprint: "A1B2 C3D4 E5F6 0718", heard_at: "2026-10-21T12:00:00Z" };

function menu(key: typeof theirs | null) {
  const wrapper = mount(KeyMenu, { props: { call: "OH2RDG", theirs: key }, attachTo: document.body });
  return { wrapper, button: wrapper.find("button.route-button") };
}

describe("the Key menu of a conversation", () => {
  it("is a button like Route, closed, and says in its box that the station has not sent its key, with Send my key as the one thing to do", async () => {
    const { wrapper, button } = menu(null);
    expect(button.text()).toBe("Key");
    expect(button.find(".route-dot").exists()).toBe(false);
    expect(wrapper.find(".route-box").exists()).toBe(false);
    await button.trigger("click");
    expect(wrapper.find(".keybox-line").text()).toBe("OH2RDG has not sent its key");
    expect(wrapper.findAll(".keybox-buttons button").map((b) => b.text())).toEqual(["Send my key"]);
    await wrapper.find(".keybox-buttons button").trigger("click");
    expect(wrapper.emitted("sendKey")).toEqual([["OH2RDG"]]);
    wrapper.unmount();
  });

  it("shows the station's key as its fingerprint and when it was heard, with a dot on the button, and Forget key asks twice", async () => {
    const { wrapper, button } = menu(theirs);
    expect(button.find(".route-dot").exists()).toBe(true);
    await button.trigger("click");
    expect(wrapper.find(".keybox-line .mono").text()).toBe("A1B2 C3D4 E5F6 0718");
    expect(wrapper.find(".keybox-line .muted").text()).toMatch(/^heard /);
    const [send, forget] = wrapper.findAll(".keybox-buttons button");
    expect(send?.text()).toBe("Send my key");
    expect(forget?.text()).toMatch(/^Forget key/); // (TwoWords holds "sure?" too, hidden until the first press)
    await forget?.trigger("click");
    expect(wrapper.emitted("forget")).toBeUndefined();
    expect(forget?.classes()).toContain("danger");
    await forget?.trigger("click");
    expect(wrapper.emitted("forget")).toEqual([["OH2RDG"]]);
    wrapper.unmount();
  });
});
