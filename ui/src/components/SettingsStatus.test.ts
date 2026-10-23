import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import type { Command } from "@/protocol/protocol";
import { configValues } from "@/test/fixtures";

function make(extra: Record<string, string> = {}) {
  const send = vi.fn((_command: Command) => true);
  const wrapper = mount(SettingsForm, { props: { config: configValues(extra), lastError: null, send, scope: "beacon" } });
  const status = () => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Status");
  const labels = () =>
    status()
      ?.findAll(".field label")
      .map((l) => l.text());
  return { wrapper, send, status, labels };
}

describe("the Status group", () => {
  it("is one choice, with a word for each way the status can come", () => {
    const { wrapper } = make();
    const select = wrapper.find<HTMLSelectElement>("#set-status-source");
    expect(select.element.tagName).toBe("SELECT");
    expect(select.findAll("option").map((o) => [o.attributes("value"), o.text()])).toEqual([
      ["off", "off"],
      ["text", "a text of my own"],
      ["rig", "the frequency from my radio (rigctld)"],
    ]);
  });

  it("is only the choice while the status is off, on a fresh install", () => {
    const { labels, wrapper } = make();
    expect(labels()).toEqual(["Status"]);
    expect(wrapper.find<HTMLSelectElement>("#set-status-source").element.value).toBe("off");
  });

  it("asks for the text and how often when the choice is a text of my own", async () => {
    const { wrapper, labels } = make();
    await wrapper.find("#set-status-source").setValue("text");
    expect(labels()).toEqual(["Status", "Text", "Every"]);
    expect(wrapper.find("#set-station-status").exists()).toBe(true);
    expect(wrapper.find("#set-status-rigctld").exists()).toBe(false);
    expect(wrapper.find("#set-status-template").exists()).toBe(false);
  });

  it("asks for the rigctld, the text with {freq} and {mode}, and how often when the choice is the radio", async () => {
    const { wrapper, labels } = make();
    await wrapper.find("#set-status-source").setValue("rig");
    expect(labels()).toEqual(["Status", "Rigctld", "Text", "Every"]);
    expect(wrapper.find("#set-status-rigctld").attributes("placeholder")).toBe("127.0.0.1:4532");
    expect(wrapper.find("#set-status-template").attributes("placeholder")).toBe("QRV {freq} {mode}");
    expect(wrapper.find("#set-station-status").exists()).toBe(false);
    expect(wrapper.find("#set-status-interval_min").attributes("placeholder")).toBe("30");
    expect(wrapper.find("#set-status-interval_min").element.closest(".field")?.querySelector(".unit")?.textContent).toBe("min");
  });

  it("has the old settings as the right choice, so that an installation keeps doing what it did", () => {
    const radio = make({ "status/rigctld": "127.0.0.1:4532", "status/template": "QRV {freq} {mode}" });
    expect(radio.wrapper.find<HTMLSelectElement>("#set-status-source").element.value).toBe("rig");
    expect(radio.wrapper.find<HTMLInputElement>("#set-status-rigctld").element.value).toBe("127.0.0.1:4532");
    expect(radio.wrapper.find<HTMLInputElement>("#set-status-template").element.value).toBe("QRV {freq} {mode}");
    const text = make({ "station/status": "At the cottage" });
    expect(text.wrapper.find<HTMLSelectElement>("#set-status-source").element.value).toBe("text");
    expect(text.wrapper.find<HTMLInputElement>("#set-station-status").element.value).toBe("At the cottage");
    const both = make({ "station/status": "At the cottage", "status/rigctld": "127.0.0.1:4532" });
    expect(both.wrapper.find<HTMLSelectElement>("#set-status-source").element.value).toBe("rig");
    const chosen = make({ "station/status": "At the cottage", "status/rigctld": "127.0.0.1:4532", "status/source": "text" });
    expect(chosen.wrapper.find<HTMLSelectElement>("#set-status-source").element.value).toBe("text");
  });

  it("shows nothing as changed for an old installation, and saves the choice once it is made", async () => {
    const { wrapper, send } = make({ "status/rigctld": "127.0.0.1:4532" });
    expect(wrapper.find("button[type='submit']").attributes("disabled")).toBeDefined();
    await wrapper.find("#set-status-source").setValue("text");
    await wrapper.find("#set-station-status").setValue("QRV 145.500");
    await wrapper.find("form").trigger("submit");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "status/source": "text", "station/status": "QRV 145.500" } });
  });

  it("keeps what was typed for the other choice while the choice is changed back and forth", async () => {
    const { wrapper } = make({ "status/source": "text", "station/status": "At the cottage" });
    await wrapper.find("#set-status-source").setValue("off");
    expect(wrapper.find("#set-station-status").exists()).toBe(false);
    await wrapper.find("#set-status-source").setValue("text");
    expect(wrapper.find<HTMLInputElement>("#set-station-status").element.value).toBe("At the cottage");
  });

  it("shows the daemon's refusal of the radio without an address under the choice", async () => {
    const { wrapper } = make();
    await wrapper.find("#set-status-source").setValue("rig");
    await wrapper.find("form").trigger("submit");
    await wrapper.setProps({ lastError: { text: "set_config: status/source: the radio needs status/rigctld (host:port of a rigctld, 127.0.0.1:4532)", n: 1 } });
    expect(wrapper.find("#set-status-source").element.closest(".field")?.querySelector(".field-error")?.textContent).toContain("needs status/rigctld");
  });
});

describe("the Symbol field", () => {
  it("is one row with the picture and the name, no table or code to read", () => {
    const { wrapper } = make();
    const field = wrapper.findAll(".field").find((f) => f.find("label").text() === "Symbol");
    expect(field?.find(".symicon .stn-layer").exists()).toBe(true);
    expect(field?.find(".symbolfield-name").text()).toBe("House");
    expect(field?.find("input").exists()).toBe(false);
    expect(wrapper.find("#set-station-symbol_table").exists()).toBe(false);
    expect(wrapper.find("#set-station-symbol_code").exists()).toBe(false);
  });

  it("is changed in the picker, which sets the table and the code underneath and is saved like any change", async () => {
    const { wrapper, send } = make();
    await wrapper.find("#set-station-symbol-change").trigger("click");
    expect(wrapper.find(".sympick").exists()).toBe(true);
    await wrapper.find<HTMLInputElement>(".sympick input[type=search]").setValue("digi");
    const digi = wrapper.findAll(".sympick-symbol");
    expect(digi.map((b) => b.text())).toEqual(["Digipeater", "Digipeater"]);
    await digi[1]?.trigger("click");
    expect(wrapper.find(".sympick").exists()).toBe(false);
    expect(wrapper.find(".symbolfield-name").text()).toBe("Digipeater");
    expect(wrapper.text()).toContain("2 changed");
    await wrapper.find("form").trigger("submit");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/symbol_table": "\\", "station/symbol_code": "#" } });
  });

  it("offers a letter or a digit on the symbols that take one, and only on those", async () => {
    const { wrapper, send } = make({ "station/symbol_table": "\\", "station/symbol_code": "#" });
    const over = wrapper.find<HTMLInputElement>(".symbolfield-over input");
    expect(wrapper.find(".symbolfield-over").text()).toBe("Letter or digit on it");
    expect(over.element.value).toBe("");
    await over.setValue("s");
    expect(over.element.value).toBe("S");
    expect(wrapper.find(".symbolfield-name").text()).toBe("Digipeater");
    await wrapper.find("form").trigger("submit");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/symbol_table": "S" } });
    await over.setValue("");
    expect(wrapper.text()).not.toContain("changed");
    expect(make().wrapper.find(".symbolfield-over").exists()).toBe(false);
  });
});

describe("the (i) of a field", () => {
  it("is after the label of the fields whose meaning is not plain, and of no other", () => {
    const { wrapper } = make({ "status/source": "rig", "beacon/power_w": "5" });
    const withTip = wrapper
      .findAll(".field")
      .filter((f) => f.find(".info-toggle").exists())
      .map((f) => f.find("label").text());
    expect(withTip).toEqual([
      "Comment",
      "Power",
      "Antenna height",
      "Antenna gain",
      "Antenna direction",
      "Interval",
      "Path",
      "Status",
      "Rigctld",
      "Text",
      "Every",
    ]);
    expect(wrapper.find(".info-text").exists()).toBe(false);
  });

  it("opens beside the field it explains and says what it is, with an example", async () => {
    const { wrapper } = make({ "status/source": "rig" });
    const field = wrapper.findAll(".field").find((f) => f.find("label").text() === "Text");
    await field?.find(".info-toggle").trigger("click");
    expect(field?.find(".info-text").text()).toContain("{freq}");
    expect(field?.find(".info-text").text()).toContain("Example: QRV {freq} {mode} gives QRV 14.074 MHz USB");
  });
});
