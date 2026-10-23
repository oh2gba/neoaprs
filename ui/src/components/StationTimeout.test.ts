import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StationTimeout from "@/components/StationTimeout.vue";
import type { Aging } from "@/lib/aging";

function field(own: [string, number][] = [], defaultMin = 1440) {
  const aging: Aging = { timeouts: new Map(own), defaultMin };
  return mount(StationTimeout, { props: { call: "OH2RDG", aging } });
}

describe("StationTimeout", () => {
  it("shows the default as the placeholder when the station has no timeout of its own, and nothing else", () => {
    const wrapper = field();
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("");
    expect(wrapper.find("label").text()).toBe("Hide from map after");
    expect(wrapper.find("input").attributes("placeholder")).toBe("1 d (usual)");
    expect(field([], 180).find("input").attributes("placeholder")).toBe("3 h (usual)");
    expect(field([], 0).find("input").attributes("placeholder")).toBe("never (usual)");
    expect(wrapper.find("input").attributes("title")).toBe("Minutes, or never; empty for the usual time");
    expect(wrapper.find("button").exists()).toBe(false);
    expect(wrapper.find("p").exists()).toBe(false);
    expect(wrapper.find(".hint").exists()).toBe(false);
  });

  it("shows the station's own timeout with its unit and an x to go back to the default, and 0 as never", () => {
    const wrapper = field([["OH2RDG", 45]]);
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("45");
    expect(wrapper.text()).toContain("min");
    expect(wrapper.find("button").text()).toBe("×");
    expect(wrapper.find("button").attributes("aria-label")).toBe("Use the default timeout");
    const never = field([["OH2RDG", 0]]);
    expect(never.find<HTMLInputElement>("input").element.value).toBe("never");
    expect(never.text()).not.toContain("min");
    expect(never.find("button").exists()).toBe(true);
  });

  it("saves the minutes when the field is left, and 0 or never as never", async () => {
    const wrapper = field();
    await wrapper.find("input").setValue(" 90 ");
    expect(wrapper.emitted("set")).toEqual([["OH2RDG", 90]]);
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("90");
    await wrapper.find("input").setValue("0");
    expect(wrapper.emitted("set")?.[1]).toEqual(["OH2RDG", 0]);
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("never");
    await wrapper.find("input").setValue("Never");
    expect(wrapper.emitted("set")?.[2]).toEqual(["OH2RDG", 0]);
  });

  it("takes the timeout away when the field is emptied, but only if there is one", async () => {
    const none = field();
    await none.find("input").trigger("change");
    expect(none.emitted("clear")).toBeUndefined();
    const own = field([["OH2RDG", 30]]);
    await own.find("input").setValue("");
    expect(own.emitted("clear")).toEqual([["OH2RDG"]]);
    await own.find("button").trigger("click");
    expect(own.emitted("clear")).toHaveLength(2);
  });

  it("saves nothing that is not changed, and nothing that is no number of minutes", async () => {
    const wrapper = field([["OH2RDG", 30]]);
    await wrapper.find("input").setValue("30");
    expect(wrapper.emitted("set")).toBeUndefined();
    for (const bad of ["soon", "-5", "1.5"]) {
      await wrapper.find("input").setValue(bad);
      expect(wrapper.find("input").classes()).toContain("invalid");
      expect(wrapper.find("input").attributes("title")).toBe("Whole minutes, or never");
    }
    expect(wrapper.emitted("set")).toBeUndefined();
    expect(wrapper.emitted("clear")).toBeUndefined();
  });

  it("follows the daemon when the timeout changes", async () => {
    const wrapper = field([["OH2RDG", 30]]);
    await wrapper.setProps({ aging: { timeouts: new Map([["OH2RDG", 45]]), defaultMin: 1440 } });
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("45");
  });
});
