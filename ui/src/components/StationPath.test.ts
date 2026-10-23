import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StationPath from "@/components/StationPath.vue";

function path(paths: [string, string][] = []) {
  return mount(StationPath, { props: { call: "OH2RDG", paths: new Map(paths), fallback: "WIDE1-1,WIDE2-1" } });
}

describe("StationPath", () => {
  it("shows the default path with (default) when the station has none of its own", () => {
    const wrapper = path();
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("WIDE1-1,WIDE2-1");
    expect(wrapper.text()).toContain("(default)");
    expect(wrapper.find(".use-default").exists()).toBe(false);
    expect(wrapper.find("p").exists()).toBe(false);
  });

  it("shows the station's own path, an empty one as direct, without (default)", () => {
    const own = path([["OH2RDG", "OH2RCH-2"]]);
    expect(own.find<HTMLInputElement>("input").element.value).toBe("OH2RCH-2");
    expect(own.text()).not.toContain("(default)");
    const direct = path([["OH2RDG", ""]]);
    expect(direct.find<HTMLInputElement>("input").element.value).toBe("");
    expect(direct.find("input").attributes("placeholder")).toBe("direct");
    expect(direct.text()).not.toContain("(default)");
  });

  it("saves what was typed when the field is left, written the way the frame carries it", async () => {
    const wrapper = path();
    await wrapper.find("input").setValue(" oh2rch-2 , wide2-1 ");
    expect(wrapper.emitted("set")).toEqual([["OH2RDG", "OH2RCH-2,WIDE2-1"]]);
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("OH2RCH-2,WIDE2-1");
  });

  it("saves an empty path as a path (direct)", async () => {
    const wrapper = path();
    await wrapper.find("input").setValue("");
    expect(wrapper.emitted("set")).toEqual([["OH2RDG", ""]]);
  });

  it("saves nothing that is not changed, and nothing that is no path", async () => {
    const wrapper = path([["OH2RDG", "OH2RCH-2"]]);
    await wrapper.find("input").trigger("change");
    await wrapper.find("input").setValue("OH2RCH-2");
    expect(wrapper.emitted("set")).toBeUndefined();
    await wrapper.find("input").setValue("not a call");
    expect(wrapper.emitted("set")).toBeUndefined();
    expect(wrapper.find("input").classes()).toContain("invalid");
    expect(wrapper.find("input").attributes("title")).toContain("separated by commas");
  });

  it("explains nothing in sentences: a field, a mark, a button, no text of its own", () => {
    for (const wrapper of [
      path(),
      path([["OH2RDG", "OH2RCH-2"]]),
      mount(StationPath, { props: { call: "OH2RDG", paths: new Map(), fallback: "", suggested: "OH2RCH-2" } }),
    ]) {
      expect(wrapper.find(".hint").exists()).toBe(false);
      expect(wrapper.find("p").exists()).toBe(false);
      expect(wrapper.text().length).toBeLessThan(40);
    }
  });

  it("takes the station's own path away with the x", async () => {
    const wrapper = path([["OH2RDG", "OH2RCH-2"]]);
    expect(wrapper.find(".use-default").text()).toBe("×");
    expect(wrapper.find(".use-default").attributes("aria-label")).toBe("Use the default path");
    await wrapper.find(".use-default").trigger("click");
    expect(wrapper.emitted("clear")).toEqual([["OH2RDG"]]);
  });

  it("follows the path it is given and the station it is for", async () => {
    const wrapper = path();
    await wrapper.setProps({ paths: new Map([["OH2RDG", "WIDE2-2"]]) });
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("WIDE2-2");
    await wrapper.setProps({ call: "OH2XYZ" });
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("WIDE1-1,WIDE2-1");
  });

  describe("the suggested path", () => {
    const suggest = (suggested: string | null, paths: [string, string][] = []) =>
      mount(StationPath, { props: { call: "OH2RDG", paths: new Map(paths), fallback: "WIDE1-1,WIDE2-1", suggested } });

    it("is no chip while there is no suggestion", () => {
      const wrapper = suggest(null);
      expect(wrapper.find(".use-suggested").exists()).toBe(false);
      expect(wrapper.find("input").attributes("placeholder")).toBe("direct");
    });

    it("is a chip that says what is suggested, fills the field with it and saves it", async () => {
      const wrapper = suggest("OH2RCH-3,OH2RCH-1");
      expect(wrapper.find(".use-suggested").text()).toBe("suggested: OH2RCH-3,OH2RCH-1");
      await wrapper.find(".use-suggested").trigger("click");
      expect(wrapper.emitted("set")).toEqual([["OH2RDG", "OH2RCH-3,OH2RCH-1"]]);
      expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("OH2RCH-3,OH2RCH-1");
    });

    it("saves direct as an empty path when direct is what is suggested", async () => {
      const wrapper = suggest("");
      expect(wrapper.find(".use-suggested").text()).toBe("suggested: direct");
      await wrapper.find(".use-suggested").trigger("click");
      expect(wrapper.emitted("set")).toEqual([["OH2RDG", ""]]);
    });

    it("keeps the placeholder at direct whatever is suggested", () => {
      expect(suggest("OH2RCH-2").find("input").attributes("placeholder")).toBe("direct");
    });

    it("is gone once the station has that path, and back when it has another", async () => {
      const wrapper = suggest("OH2RCH-2", [["OH2RDG", "OH2RCH-2"]]);
      expect(wrapper.find(".use-suggested").exists()).toBe(false);
      await wrapper.setProps({ paths: new Map([["OH2RDG", "WIDE2-1"]]) });
      expect(wrapper.find(".use-suggested").exists()).toBe(true);
    });
  });
});
