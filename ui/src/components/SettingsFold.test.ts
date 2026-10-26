import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsFold from "@/components/SettingsFold.vue";
import { useSettingsForm } from "@/composables/useSettingsForm";
import { fakeDaemon } from "@/test/context";
import { configValues } from "@/test/fixtures";

// The fold on its own, over the real settings and form of a page whose daemon is a record of the commands: what it makes of each kind of key, and what it does with what is typed, chosen and cancelled.
function make(keys: readonly string[], extra: Record<string, string> = {}, disabled?: (key: string) => boolean) {
  const daemon = fakeDaemon({ config: configValues(extra) });
  const config = daemon.config;
  const form = useSettingsForm(config, daemon.settings, "beacon", () => false);
  const wrapper = mount(SettingsFold, {
    props: { title: "Antenna", keys, settings: daemon.settings, form, defaults: form.defaults.value, disabled },
    attachTo: document.body,
  });
  return { wrapper, daemon, form };
}

const sent = (daemon: ReturnType<typeof make>["daemon"]) => daemon.send.mock.calls.map(([command]) => command);

describe("SettingsFold", () => {
  it("shows nothing when it has no keys", () => {
    const { wrapper } = make([]);
    expect(wrapper.find("details").exists()).toBe(false);
  });

  it("is a closed heading with the fields of its keys under it, each with its label", () => {
    const { wrapper } = make(["beacon/power_w", "beacon/antenna_height_m"], { "beacon/power_w": "5" });
    const fold = wrapper.find("details.settings-fold");
    expect(fold.attributes("open")).toBeUndefined();
    expect(fold.find("summary").text()).toBe("Antenna");
    expect(wrapper.findAll(".field > label").map((l) => l.text())).toEqual(["Power", "Antenna height"]);
  });

  it("types into a field and sends it when it is left, and Esc puts the value in force back", async () => {
    const { wrapper, daemon } = make(["beacon/power_w"], { "beacon/power_w": "5" });
    const field = wrapper.find<HTMLInputElement>("#set-beacon-power_w");
    await field.setValue("9");
    expect(daemon.settings.draft["beacon/power_w"]).toBe("9");
    expect(sent(daemon)).toEqual([]);
    await field.trigger("keydown", { key: "Escape" });
    expect(daemon.settings.draft["beacon/power_w"]).toBe("5");
    await field.setValue("9");
    await field.trigger("blur");
    expect(sent(daemon)).toEqual([{ cmd: "set_config", values: { "beacon/power_w": "9" } }]);
    wrapper.unmount();
  });

  it("sends a choice at once and takes no typing for it", async () => {
    const { wrapper, daemon } = make(["beacon/power_w", "beacon/antenna_direction"], { "beacon/power_w": "5" });
    const choice = wrapper.find<HTMLSelectElement>("#set-beacon-antenna_direction");
    await choice.setValue("NE");
    expect(sent(daemon)).toEqual([{ cmd: "set_config", values: { "beacon/antenna_direction": "NE" } }]);
    wrapper.unmount();
  });

  it("has the path as one choice (Recommended, Direct only, Custom) in the place of a field, with the recommended path of the station's symbol", async () => {
    const { wrapper, daemon } = make(["beacon/path"], { "station/symbol_table": "/", "station/symbol_code": ">" });
    expect(wrapper.find("#set-beacon-path").exists()).toBe(true);
    expect(wrapper.findAll("option").map((o) => o.text())).toEqual(["Recommended (WIDE1-1,WIDE2-1)", "Direct only (no digipeaters)", "Custom…"]);
    await wrapper.find("select").setValue("direct");
    expect(sent(daemon)).toEqual([{ cmd: "set_config", values: { "beacon/path": "DIRECT" } }]);
    wrapper.unmount();
  });

  it("types a custom path, sends it when it is left, and Esc brings the stored one back", async () => {
    const { wrapper, daemon } = make(["beacon/path"], { "beacon/path": "WIDE2-1" });
    const typed = wrapper.find<HTMLInputElement>("#set-beacon-path-typed");
    await typed.setValue("WIDE2-2");
    expect(daemon.settings.draft["beacon/path"]).toBe("WIDE2-2");
    await typed.trigger("keydown", { key: "Escape" });
    expect(daemon.settings.draft["beacon/path"]).toBe("WIDE2-1");
    await typed.setValue("WIDE2-2");
    await typed.trigger("keydown", { key: "Enter" });
    expect(sent(daemon)).toEqual([{ cmd: "set_config", values: { "beacon/path": "WIDE2-2" } }]);
    wrapper.unmount();
  });

  it("shows a field the form greys out with its value, and leaves the fold open to the person all the same", async () => {
    const { wrapper } = make(["beacon/power_w"], { "beacon/power_w": "5" }, () => true);
    expect(wrapper.find<HTMLInputElement>("#set-beacon-power_w").element.disabled).toBe(true);
    expect(wrapper.find<HTMLInputElement>("#set-beacon-power_w").element.value).toBe("5");
    await wrapper.find("summary").trigger("click");
    expect(wrapper.find("details").element.hasAttribute("open")).toBe(true);
  });

  it("shows the reason the page found under the field, sends nothing, and the field is the one of that reason", async () => {
    const { wrapper, daemon } = make(["beacon/power_w"]);
    await wrapper.find("#set-beacon-power_w").setValue("many");
    await wrapper.find("#set-beacon-power_w").trigger("blur");
    const reason = wrapper.find("p.field-error[role='alert']");
    expect(reason.exists()).toBe(true);
    expect(reason.text()).toBe(daemon.settings.errors["beacon/power_w"]);
    expect(wrapper.find("#set-beacon-power_w").attributes("aria-invalid")).toBe("true");
    expect(sent(daemon)).toEqual([]);
    wrapper.unmount();
  });

  it("shows a key the page has no description of with its own name as the label and an empty value, and the path with no symbol chosen as the Recommended one", () => {
    const { wrapper } = make(["beacon/not_a_setting"]);
    expect(wrapper.find(".field > label").text()).toBe("beacon/not_a_setting");
    expect(wrapper.find<HTMLInputElement>("#set-beacon-not_a_setting").element.value).toBe("");
    const bare = make(["beacon/path"], { "station/symbol_table": "", "station/symbol_code": "" });
    expect(bare.wrapper.find<HTMLSelectElement>("select").element.value).toBe("recommended");
    wrapper.unmount();
    bare.wrapper.unmount();
  });
});
