import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SendButton from "@/components/SendButton.vue";
import { shown } from "@/test/shown";

describe("SendButton", () => {
  it("holds both of its words, so that the first press moves nothing", async () => {
    const wrapper = mount(SendButton, { props: { label: "Send status now", armed: false, disabled: false } });
    const faces = () => wrapper.findAll(".twowords > span").map((face) => face.text());
    expect(faces()).toEqual(["Send status now", "Really send?"]);
    expect(shown(wrapper)).toBe("Send status now");
    await wrapper.setProps({ armed: true });
    expect(faces()).toEqual(["Send status now", "Really send?"]);
    expect(shown(wrapper)).toBe("Really send?");
  });
});
