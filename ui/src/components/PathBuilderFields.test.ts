// The path builder from each field a path is typed in: a station's Route (StationPath, in a conversation and in the Stations tab's panel), the beacon's path (SettingsPath), the Path of Ask around and of Local info (RequestPath) and
// the path of an object (ObjectForm). Use puts the path into the field, which saves it as it saves what is typed; Cancel leaves the field as it was.
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import ObjectForm from "@/components/ObjectForm.vue";
import RequestPath from "@/components/RequestPath.vue";
import SettingsPath from "@/components/SettingsPath.vue";
import StationPath from "@/components/StationPath.vue";
import { useOwnObjects } from "@/composables/useOwnObjects";
import type { Panel } from "@/composables/usePanel";
import { FIELDS } from "@/lib/settings";

const dialog = (): HTMLElement | null => document.body.querySelector<HTMLElement>(".pathbuild");
const button = (text: string): HTMLButtonElement | undefined =>
  [...(dialog()?.querySelectorAll<HTMLButtonElement>("button") ?? [])].find((b) => (b.textContent ?? "").trim() === text);
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function pick(...texts: string[]): Promise<void> {
  for (const text of texts) {
    button(text)?.click();
    await flush();
  }
}

afterEach(() => (document.body.innerHTML = ""));

describe("the path builder of each path field", () => {
  it("of a station's Route starts from the path in force and saves the path built as the station's own", async () => {
    const wrapper = mount(StationPath, { props: { call: "OH2DPN", paths: new Map(), fallback: "WIDE1-1,WIDE2-1" }, attachTo: document.body });
    await wrapper.find("button.pathbuild-open").trigger("click");
    expect(dialog()?.querySelector("output")?.textContent).toBe("WIDE1-1,WIDE2-1");
    expect(button("As its packets come")).toBeDefined();
    await pick("3", "Cancel");
    expect(wrapper.emitted("set")).toBeUndefined();
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("");
    await wrapper.find("button.pathbuild-open").trigger("click");
    await pick("1", "Use");
    expect(wrapper.emitted("set")).toEqual([["OH2DPN", "WIDE1-1"]]);
    expect(wrapper.find<HTMLInputElement>("input").element.value).toBe("WIDE1-1");
    await wrapper.find("button.pathbuild-open").trigger("click");
    await pick("Direct", "Use");
    expect(wrapper.emitted("set")?.[1]).toEqual(["OH2DPN", "DIRECT"]);
  });

  it("of the beacon's path starts from the recommended one, is held to the setting's rule and applies at once", async () => {
    const wrapper = mount(SettingsPath, {
      props: { id: "set-beacon-path", info: FIELDS["beacon/path"], modelValue: "", error: "", changed: false, recommended: "WIDE2-1" },
      attachTo: document.body,
    });
    await wrapper.find("button.pathbuild-open").trigger("click");
    expect(dialog()?.querySelector("output")?.textContent).toBe("WIDE2-1");
    expect(button("As its packets come")).toBeUndefined();
    await pick("2", "Cancel");
    expect(wrapper.emitted("choose")).toBeUndefined();
    await wrapper.find("button.pathbuild-open").trigger("click");
    await pick("2", "Use");
    expect(wrapper.emitted("choose")).toEqual([["WIDE2-2"]]);
    await wrapper.setProps({ modelValue: "WIDE2-2" });
    expect(wrapper.find<HTMLSelectElement>("select").element.value).toBe("custom");
    await wrapper.find("button.pathbuild-open").trigger("click");
    await pick("Direct", "Use");
    expect(wrapper.emitted("choose")?.[1]).toEqual(["DIRECT"]);
    await wrapper.setProps({ modelValue: "DIRECT" });
    expect(wrapper.find<HTMLSelectElement>("select").element.value).toBe("direct");
  });

  it("of the beacon's path is off while the field is", () => {
    const wrapper = mount(SettingsPath, {
      props: { id: "set-beacon-path", info: FIELDS["beacon/path"], modelValue: "", error: "", changed: false, recommended: "WIDE2-1", disabled: true },
    });
    expect(wrapper.find("button.pathbuild-open").attributes("disabled")).toBeDefined();
  });

  it("of a request's Path gives it the path built, with no room for one too long for RF only", async () => {
    const wrapper = mount(RequestPath, { props: { path: "", rfOnly: true, usual: "", problem: "" }, attachTo: document.body });
    expect(wrapper.find("input[type='text']").attributes("placeholder")).toBe("direct");
    await wrapper.find("button.pathbuild-open").trigger("click");
    expect(dialog()?.querySelector("output")?.textContent).toBe("DIRECT");
    const input = dialog()?.querySelector<HTMLInputElement>(".pathbuild-type input");
    if (!input) throw new Error("no field to type a hop into");
    input.value = "A1,B2,C3,D4,E5,F6,G7,H8";
    input.dispatchEvent(new Event("input"));
    await flush();
    await pick("Add");
    expect(button("Use")?.disabled).toBe(true);
    expect(button("Use")?.title).toContain("RF only");
    await pick("Direct", "1", "Use");
    expect(wrapper.emitted("update:path")).toEqual([["WIDE1-1"]]);
  });

  it("of an object puts the path built into the form", async () => {
    const view = useOwnObjects(new Map(), () => true, { show: vi.fn(), tab: ref("objects") } as unknown as Panel);
    const wrapper = mount(ObjectForm, { props: { form: view, fallbackPath: "WIDE1-1,WIDE2-1" }, attachTo: document.body });
    const opener = wrapper.findAll("button.pathbuild-open");
    expect(opener).toHaveLength(1);
    await opener[0]?.trigger("click");
    await pick("1", "Cancel");
    expect(view.draft.path).toBe("");
    await opener[0]?.trigger("click");
    await pick("1", "Use");
    expect(view.draft.path).toBe("WIDE1-1");
  });
});
