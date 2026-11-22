import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import LevelBar from "@/components/LevelBar.vue";

describe("LevelBar", () => {
  it("is a meter with its value for a screen reader: the percent of the bar, and the number shown as its words", () => {
    const wrapper = mount(LevelBar, {
      props: { id: "lvl", label: "Receive level", percent: 42.6, zone: "ok", good: [30, 60], held: false, value: "-18 dBFS" },
    });
    const meter = wrapper.find("[role='meter']");
    expect([
      meter.attributes("aria-valuemin"),
      meter.attributes("aria-valuemax"),
      meter.attributes("aria-valuenow"),
      meter.attributes("aria-valuetext"),
    ]).toEqual(["0", "100", "43", "-18 dBFS"]);
  });
});
