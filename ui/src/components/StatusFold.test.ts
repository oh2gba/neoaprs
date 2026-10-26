import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StatusFold from "@/components/StatusFold.vue";

describe("StatusFold", () => {
  it("is one row: the state in its tone, then the quiet detail", () => {
    const wrapper = mount(StatusFold, { props: { state: "off", tone: "tnc-waiting", line: "RX only: nothing is sent" } });
    expect(wrapper.find(".statetext").classes()).toContain("tnc-waiting");
    expect(wrapper.find(".tncstatus").text()).toBe("RX only: nothing is sent");
  });
});
