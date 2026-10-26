// The (i) beside the Settings tab's fields that a non-developer may not understand: closed until clicked, then a few plain sentences.
import { DOMWrapper, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { FIELDS } from "@/lib/settings";
import SettingsField from "@/components/SettingsField.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues, mapState } from "@/test/fixtures";

const NETWORK = { "web/network": "true", "web/key": "k7m2-x9pq-4hrt" };

function make(extra: Record<string, string> = {}, urls: string[] = []) {
  const config = configValues(extra);
  config.urls = urls;
  return mount(SettingsForm, { global: withDaemon(fakeDaemon({ config, map: mapState() })) });
}

/** The (i) of the row that holds the control with this id. */
const tipOf = (wrapper: ReturnType<typeof make>, id: string) =>
  wrapper.find(`#${id}`).element.closest(".field")?.querySelector<HTMLButtonElement>(".info-toggle") ?? null;

describe("the (i) of the Settings tab", () => {
  const cases: [string, string, RegExp][] = [
    ["set-web-network", "About network access", /phone, a tablet or a laptop on your network.*access key and the addresses/s],
    ["set-web-key", "About the access key", /type it once on each.*New key logs every other device out/s],
    ["set-web-url-0", "About the addresses", /same network.*\.local/s],
    ["set-tnc-profile", "Which radio type to pick", /How NeoAPRS talks to your radio.*KISS TNC.*KISS over TCP.*docs\/RADIOS\.md/s],
    ["set-serial-port", "About the port", /Automatic looks for it.*\/dev\/ttyUSB0.*COM3.*Refresh reads the list again/s],
    ["set-serial-baud", "About the speed", /Leave it empty.*57600 for a NinoTNC/s],
    ["set-map-radius_km", "About the radius", /bigger download.*150 km is a region/s],
    ["set-update-now", "About the update check", /Once a day NeoAPRS asks/],
  ];

  it.each(cases)("%s has an (i) called %s that opens to the text and closes on Escape", async (id, label, text) => {
    const wrapper = make(NETWORK, ["http://192.168.1.20:7303/"]);
    const toggle = tipOf(wrapper, id);
    expect(toggle, id).not.toBeNull();
    expect(toggle?.getAttribute("aria-label")).toBe(label);
    expect(wrapper.find(".info-text").exists()).toBe(false);
    const button = new DOMWrapper(toggle);
    await button.trigger("click");
    expect(wrapper.find(".info-text").text()).toMatch(text);
    await new DOMWrapper(button.element.closest(".infotip")).trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".info-text").exists()).toBe(false);
  });

  it("explains the two alerts under the heading of the NeoAPRS computer: its own command, and the browser's sound and pop-up", async () => {
    const wrapper = make();
    await wrapper.find<HTMLButtonElement>("fieldset.subbox > legend .info-toggle").trigger("click");
    const text = wrapper.find(".info-text").text();
    expect(text).toMatch(/runs the Command for each new message.*a sound and a notification/s);
    expect(text).toMatch(/next group is this browser/);
  });

  it("keeps every text to one or two short lines and puts none under a field", () => {
    for (const [key, info] of Object.entries(FIELDS)) {
      if (!info.tip) continue;
      expect(info.tip.length, key).toBeLessThanOrEqual(2);
      expect(Math.max(...info.tip.map((line) => line.length)), key).toBeLessThanOrEqual(125);
    }
    const wrapper = make(NETWORK);
    expect(wrapper.findAll(".field p")).toHaveLength(0);
    expect(wrapper.find(".info-text").exists()).toBe(false);
  });

  it("has a one-line (i) on the alert and its command too, which the group's (i) explains further", async () => {
    const wrapper = make();
    for (const id of ["set-messages-alert_command", "set-messages-alert"]) expect(tipOf(wrapper, id), id).not.toBeNull();
    await new DOMWrapper(tipOf(wrapper, "set-messages-alert_command")).trigger("click");
    expect(wrapper.find(".info-text").text()).toContain("NEOAPRS_FROM and NEOAPRS_TEXT");
  });

  it("shows a plain on/off setting as a checkbox that sends true or false", async () => {
    const config = configValues();
    const daemon = fakeDaemon({ config });
    const send = daemon.send;
    const wrapper = mount(SettingsForm, { global: withDaemon(daemon) });
    const box = wrapper.find<HTMLInputElement>("#set-messages-alert");
    expect(box.attributes("type")).toBe("checkbox");
    expect(box.element.checked).toBe(true);
    await box.setValue(false);
    await wrapper.find("form").trigger("submit");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "messages/alert": "false" } });
  });
});

describe("the pictures in the notes of the Settings fields", () => {
  const withPicture: [string, string][] = [
    ["beacon/interval_min", "beacon"],
    ["beacon/path", "path"],
    ["status/source", "status"],
    ["station/call", "ssid"],
    ["web/network", "network"],
    ["web/key", "accesskey"],
    ["map/radius_km", "radius"],
    ["digi/enabled", "digipeater"],
    ["gps/source", "position"],
  ];

  it.each(withPicture)("%s shows the picture %s under its text", async (key, picture) => {
    const info = FIELDS[key];
    expect(info?.picture).toBe(picture);
    const wrapper = mount(SettingsField, {
      props: { id: "f", info, modelValue: "", fallback: "", error: "", changed: false },
      attachTo: document.body,
    });
    await wrapper.find(".info-toggle").trigger("click");
    expect(wrapper.find(".info-text svg").attributes("data-picture")).toBe(picture);
    wrapper.unmount();
  });

  it("no other field of the settings has one: a picture only where it says more than the words", () => {
    expect(
      Object.entries(FIELDS)
        .filter(([, info]) => info.picture !== undefined)
        .map(([key]) => key)
        .sort(),
    ).toEqual(withPicture.map(([key]) => key).sort());
  });
});
