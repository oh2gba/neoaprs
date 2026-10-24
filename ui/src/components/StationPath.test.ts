import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import StationPath from "@/components/StationPath.vue";

function path(paths: [string, string][] = [], heard: string | null = null, fallback = "WIDE1-1,WIDE2-1") {
  return mount(StationPath, { props: { call: "OH2RDG", paths: new Map(paths), fallback, heard } });
}

const line = (wrapper: ReturnType<typeof path>) => wrapper.find(".path-line").text();

describe("StationPath", () => {
  it("has an empty field and says on one line what the automatic choice is, when the station has no path of its own", () => {
    const wrapper = path();
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("");
    expect(wrapper.find("input").attributes("placeholder")).toBe("automatic");
    expect(wrapper.find(".use-default").exists()).toBe(false);
    expect(line(wrapper)).toBe("Automatic: WIDE1-1,WIDE2-1");
    expect(wrapper.find("p").exists()).toBe(false);
  });

  describe("the line of the automatic choice", () => {
    it("names the path lately heard, then the beacon's", () => {
      expect(line(path([], "OH2RDG,OH2RCH-2"))).toBe("Automatic: via OH2RDG,OH2RCH-2, then WIDE1-1,WIDE2-1");
    });

    it("says direct, then the beacon's path, when the station is heard direct", () => {
      expect(line(path([], ""))).toBe("Automatic: direct, then WIDE1-1,WIDE2-1");
    });

    it("is the beacon's path alone when nothing has been heard", () => {
      expect(line(path([], null))).toBe("Automatic: WIDE1-1,WIDE2-1");
    });

    it("says direct for a beacon path that is direct only, and does not repeat itself", () => {
      expect(line(path([], null, ""))).toBe("Automatic: direct");
      expect(line(path([], "", ""))).toBe("Automatic: direct");
      expect(line(path([], "OH2RCH-2", ""))).toBe("Automatic: via OH2RCH-2, then direct");
    });

    it("does not say the same path twice", () => {
      expect(line(path([], "WIDE1-1,WIDE2-1"))).toBe("Automatic: WIDE1-1,WIDE2-1");
    });
  });

  it("shows the station's own path in the field, and the line says it is yours", () => {
    const wrapper = path([["OH2RDG", "OH2RCH-2"]], "OH2RDG");
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("OH2RCH-2");
    expect(line(wrapper)).toBe("Your path: OH2RCH-2");
    expect(wrapper.find(".use-default").exists()).toBe(true);
  });

  it("shows an own path with no digipeaters as DIRECT", () => {
    const wrapper = path([["OH2RDG", ""]]);
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("DIRECT");
    expect(line(wrapper)).toBe("Your path: direct");
  });

  it("saves what was typed when the field is left, written the way the frame carries it", async () => {
    const wrapper = path();
    await wrapper.find("input").setValue(" oh2rch-2 , wide2-1 ");
    expect(wrapper.emitted("set")).toEqual([["OH2RDG", "OH2RCH-2,WIDE2-1"]]);
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("OH2RCH-2,WIDE2-1");
  });

  it("saves the word direct as the word, never an empty path", async () => {
    const wrapper = path();
    await wrapper.find("input").setValue("direct");
    expect(wrapper.emitted("set")).toEqual([["OH2RDG", "DIRECT"]]);
    expect(wrapper.emitted("clear")).toBeUndefined();
  });

  it("gives the choice back to the automatic one when the field is emptied", async () => {
    const wrapper = path([["OH2RDG", "OH2RCH-2"]]);
    await wrapper.find("input").setValue("  ");
    expect(wrapper.emitted("clear")).toEqual([["OH2RDG"]]);
    expect(wrapper.emitted("set")).toBeUndefined();
  });

  it("sends nothing for an empty field when the station has no path of its own", async () => {
    const wrapper = path();
    await wrapper.find("input").trigger("change");
    expect(wrapper.emitted("set")).toBeUndefined();
    expect(wrapper.emitted("clear")).toBeUndefined();
  });

  it("saves nothing that is not changed, and nothing that is no path (DIRECT among calls is none)", async () => {
    const wrapper = path([["OH2RDG", "OH2RCH-2"]]);
    await wrapper.find("input").trigger("change");
    await wrapper.find("input").setValue("OH2RCH-2");
    expect(wrapper.emitted("set")).toBeUndefined();
    await wrapper.find("input").setValue("not a call");
    expect(wrapper.emitted("set")).toBeUndefined();
    expect(wrapper.find("input").classes()).toContain("invalid");
    expect(wrapper.find("input").attributes("title")).toContain("separated by commas");
    await wrapper.find("input").setValue("DIRECT,WIDE1-1");
    expect(wrapper.emitted("set")).toBeUndefined();
  });

  it("explains nothing in sentences: a field, a mark, a button and the one line", () => {
    for (const wrapper of [path(), path([["OH2RDG", "OH2RCH-2"]]), path([], "OH2RCH-2")]) {
      expect(wrapper.find(".hint").exists()).toBe(false);
      expect(wrapper.find("p").exists()).toBe(false);
      expect(wrapper.find(".use-suggested").exists()).toBe(false);
      expect(wrapper.text().length).toBeLessThan(80);
    }
  });

  it("takes the station's own path away with the x", async () => {
    const wrapper = path([["OH2RDG", "OH2RCH-2"]]);
    expect(wrapper.find(".use-default").text()).toBe("×");
    expect(wrapper.find(".use-default").attributes("aria-label")).toBe("Automatic path");
    await wrapper.find(".use-default").trigger("click");
    expect(wrapper.emitted("clear")).toEqual([["OH2RDG"]]);
  });

  it("follows the path it is given and the station it is for", async () => {
    const wrapper = path();
    await wrapper.setProps({ paths: new Map([["OH2RDG", "WIDE2-2"]]) });
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("WIDE2-2");
    expect(line(wrapper)).toBe("Your path: WIDE2-2");
    await wrapper.setProps({ call: "OH2XYZ" });
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("");
    expect(line(wrapper)).toBe("Automatic: WIDE1-1,WIDE2-1");
  });
});
