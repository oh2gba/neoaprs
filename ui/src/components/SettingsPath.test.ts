import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsPath from "@/components/SettingsPath.vue";
import { FIELDS } from "@/lib/settings";

function make(value: string, over: Record<string, unknown> = {}) {
  return mount(SettingsPath, {
    props: { id: "set-beacon-path", info: FIELDS["beacon/path"], modelValue: value, error: "", changed: false, recommended: "WIDE1-1,WIDE2-1", ...over },
  });
}

const select = (wrapper: ReturnType<typeof make>) => wrapper.find<HTMLSelectElement>("select");
const typed = (wrapper: ReturnType<typeof make>) => wrapper.find<HTMLInputElement>("#set-beacon-path-typed");

describe("SettingsPath", () => {
  it("offers the recommended path, direct only and a custom one", () => {
    const wrapper = make("");
    expect(wrapper.findAll("option").map((o) => [o.attributes("value"), o.text()])).toEqual([
      ["recommended", "Recommended (WIDE1-1,WIDE2-1)"],
      ["direct", "Direct only (no digipeaters)"],
      ["custom", "Custom…"],
    ]);
  });

  it("names the recommended path of a fixed station, and follows the symbol when it changes", async () => {
    const wrapper = make("", { recommended: "WIDE2-1" });
    expect(wrapper.findAll("option")[0]?.text()).toBe("Recommended (WIDE2-1)");
    await wrapper.setProps({ recommended: "WIDE1-1,WIDE2-1" });
    expect(wrapper.findAll("option")[0]?.text()).toBe("Recommended (WIDE1-1,WIDE2-1)");
    expect(select(wrapper).element.value).toBe("recommended");
  });

  it("shows the empty setting as Recommended, with no field", () => {
    const wrapper = make("");
    expect(select(wrapper).element.value).toBe("recommended");
    expect(typed(wrapper).exists()).toBe(false);
  });

  it.each([["WIDE1-1,WIDE2-1"], ["WIDE2-1"]])("shows the path %j that is typed in as Custom: the path of the setting is what is stored", (value) => {
    const wrapper = make(value);
    expect(select(wrapper).element.value).toBe("custom");
    expect(typed(wrapper).element.value).toBe(value);
  });

  it("shows DIRECT as Direct only", () => {
    const wrapper = make("DIRECT");
    expect(select(wrapper).element.value).toBe("direct");
    expect(typed(wrapper).exists()).toBe(false);
  });

  it("shows any other path as Custom with its calls in the field", () => {
    const wrapper = make("WIDE2-2");
    expect(select(wrapper).element.value).toBe("custom");
    expect(typed(wrapper).element.value).toBe("WIDE2-2");
  });

  it("applies Recommended at once, as the empty setting: the daemon takes the path of the symbol", async () => {
    const wrapper = make("DIRECT", { recommended: "WIDE2-1" });
    await select(wrapper).setValue("recommended");
    expect(wrapper.emitted("choose")).toEqual([[""]]);
  });

  it("applies Direct only at once, as the word DIRECT", async () => {
    const wrapper = make("WIDE2-2");
    await select(wrapper).setValue("direct");
    expect(wrapper.emitted("choose")).toEqual([["DIRECT"]]);
    expect(typed(wrapper).exists()).toBe(false);
  });

  it("shows the field for Custom without sending anything, starting from the recommended calls", async () => {
    const wrapper = make("DIRECT");
    await select(wrapper).setValue("custom");
    expect(typed(wrapper).exists()).toBe(true);
    expect(typed(wrapper).element.value).toBe("WIDE1-1,WIDE2-1");
    expect(typed(wrapper).attributes("placeholder")).toBe("WIDE1-1,WIDE2-1");
    expect(wrapper.emitted("choose")).toBeUndefined();
    expect(wrapper.emitted("commit")).toBeUndefined();
  });

  it("sends the custom calls on Enter and when the field is left, and passes the typing on as it goes", async () => {
    const wrapper = make("WIDE2-2");
    await typed(wrapper).setValue("WIDE2-1");
    expect(wrapper.emitted("update:modelValue")).toEqual([["WIDE2-1"]]);
    expect(wrapper.emitted("commit")).toBeUndefined();
    await typed(wrapper).trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("commit")).toEqual([[null]]);
    await typed(wrapper).setValue("WIDE2-2");
    await typed(wrapper).trigger("blur");
    expect(wrapper.emitted("commit")).toHaveLength(2);
  });

  it("sends nothing when the field is left as it was", async () => {
    const wrapper = make("WIDE2-2");
    await typed(wrapper).trigger("blur");
    expect(wrapper.emitted("commit")).toBeUndefined();
  });

  it("goes back to the choice in force when Custom was picked and the field left alone", async () => {
    const wrapper = make("DIRECT");
    await select(wrapper).setValue("custom");
    await typed(wrapper).trigger("blur");
    expect(typed(wrapper).exists()).toBe(false);
    expect(select(wrapper).element.value).toBe("direct");
    expect(wrapper.emitted("commit")).toBeUndefined();
  });

  it("puts the path in force back on Esc", async () => {
    const wrapper = make("WIDE2-2", { changed: true });
    await typed(wrapper).setValue("WIDE2-1");
    await typed(wrapper).trigger("keydown", { key: "Escape" });
    expect(wrapper.emitted("cancel")).toHaveLength(1);
    expect(typed(wrapper).element.value).toBe("WIDE2-2");
  });

  it("follows the path in force when the daemon tells a new one", async () => {
    const wrapper = make("WIDE2-2");
    await wrapper.setProps({ modelValue: "DIRECT" });
    expect(select(wrapper).element.value).toBe("direct");
    expect(typed(wrapper).exists()).toBe(false);
    await wrapper.setProps({ modelValue: "WIDE2-1" });
    expect(typed(wrapper).element.value).toBe("WIDE2-1");
  });

  it("keeps a path the daemon refused in its field, with the complaint under it", async () => {
    const wrapper = make("");
    await select(wrapper).setValue("custom");
    await wrapper.setProps({ modelValue: "BAD CALL", changed: true, error: "BAD is not a call" });
    expect(typed(wrapper).exists()).toBe(true);
    expect(wrapper.find(".field-error").text()).toBe("BAD is not a call");
  });
});
