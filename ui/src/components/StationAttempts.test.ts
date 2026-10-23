import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StationAttempts from "@/components/StationAttempts.vue";
import type { Attempts } from "@/lib/attempts";

function field(own: [string, number][] = [], defaultCount = 6) {
  const attempts: Attempts = { own: new Map(own), defaultCount };
  return mount(StationAttempts, { props: { call: "OH2RDG", attempts } });
}

describe("StationAttempts", () => {
  it("shows the setting's value as the placeholder when the station has no count of its own, and nothing else", () => {
    const wrapper = field();
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("");
    expect(wrapper.find("input").attributes("placeholder")).toBe("(default: 6)");
    expect(field([], 3).find("input").attributes("placeholder")).toBe("(default: 3)");
    expect(wrapper.find("label").text()).toBe("Attempts");
    expect(wrapper.find("button").exists()).toBe(false);
    expect(wrapper.find("p").exists()).toBe(false);
    expect(wrapper.find(".hint").exists()).toBe(false);
  });

  it("shows the station's own count with an x to go back to the default", () => {
    const wrapper = field([["OH2RDG", 2]]);
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("2");
    expect(wrapper.find("button").text()).toBe("×");
    expect(wrapper.find("button").attributes("aria-label")).toBe("Use the default attempts");
  });

  it("saves the count when the field is left", async () => {
    const wrapper = field();
    await wrapper.find("input").setValue(" 2 ");
    expect(wrapper.emitted("set")).toEqual([["OH2RDG", 2]]);
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("2");
    await wrapper.find("input").setValue("10");
    expect(wrapper.emitted("set")?.[1]).toEqual(["OH2RDG", 10]);
  });

  it("takes the count away when the field is emptied, but only if there is one, and with the x", async () => {
    const none = field();
    await none.find("input").trigger("change");
    expect(none.emitted("clear")).toBeUndefined();
    const own = field([["OH2RDG", 2]]);
    await own.find("input").setValue("");
    expect(own.emitted("clear")).toEqual([["OH2RDG"]]);
    await own.find("button").trigger("click");
    expect(own.emitted("clear")).toHaveLength(2);
  });

  it("saves nothing that is not changed, and nothing that is no count from 1 to 10", async () => {
    const wrapper = field([["OH2RDG", 2]]);
    await wrapper.find("input").setValue("2");
    expect(wrapper.emitted("set")).toBeUndefined();
    for (const bad of ["0", "11", "-1", "1.5", "twice"]) {
      await wrapper.find("input").setValue(bad);
      expect(wrapper.find("input").classes()).toContain("invalid");
      expect(wrapper.find("input").attributes("title")).toBe("Whole number, 1 to 10");
    }
    expect(wrapper.emitted("set")).toBeUndefined();
    expect(wrapper.emitted("clear")).toBeUndefined();
  });

  it("follows the daemon when the count changes", async () => {
    const wrapper = field([["OH2RDG", 2]]);
    await wrapper.setProps({ attempts: { own: new Map([["OH2RDG", 4]]), defaultCount: 6 } });
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("4");
  });
});
