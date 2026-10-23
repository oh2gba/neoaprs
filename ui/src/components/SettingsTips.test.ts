// The (i) beside the Settings tab's fields that a non-developer may not understand: closed until clicked, then a few plain sentences.
import { DOMWrapper, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { FIELDS } from "@/lib/settings";
import { configValues, mapState } from "@/test/fixtures";

const NETWORK = { "web/network": "true", "web/key": "k7m2-x9pq-4hrt" };

function make(extra: Record<string, string> = {}, urls: string[] = []) {
  const config = configValues(extra);
  config.urls = urls;
  return mount(SettingsForm, { props: { config, lastError: null, send: vi.fn(() => true), map: mapState() } });
}

/** The (i) of the row that holds the control with this id. */
const tipOf = (wrapper: ReturnType<typeof make>, id: string) =>
  wrapper.find(`#${id}`).element.closest(".field")?.querySelector<HTMLButtonElement>(".info-toggle") ?? null;

describe("the (i) of the Settings tab", () => {
  const cases: [string, string, RegExp][] = [
    [
      "set-web-network",
      "About network access",
      /other devices on your network.*access key appears.*Type the key once on each device.*plain http.*not for the internet/s,
    ],
    ["set-web-key", "About the access key", /type this key once.*New key.*logs every other device out/s],
    ["set-web-url-0", "About the addresses", /same network as NeoAPRS.*\.local/s],
    ["set-tnc-profile", "Which radio type to pick", /KISS TNC: Mobilinkd.*KISS over TCP: Direwolf.*Kenwood TH-D7.*radio guide/s],
    ["set-serial-port", "About the port", /automatic.*\/dev\/ttyUSB0.*COM3.*Bluetooth radio appears in this list after you have paired/s],
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
    await wrapper.find<HTMLButtonElement>("h3.subgroup .info-toggle").trigger("click");
    const text = wrapper.find(".info-text").text();
    expect(text).toMatch(/runs the Command when a message arrives.*runs on another computer, that is where it sounds/s);
    expect(text).toMatch(/a sound, a sound and a pop-up, or a pop-up only/);
  });

  it("keeps every text to a few plain sentences and puts none under a field", () => {
    for (const [key, info] of Object.entries(FIELDS)) {
      if (!info.tip) continue;
      expect(info.tip.join(" ").length, key).toBeLessThan(700);
      expect(info.tip.length, key).toBeLessThanOrEqual(5);
    }
    const wrapper = make(NETWORK);
    expect(wrapper.findAll(".field p")).toHaveLength(0);
    expect(wrapper.find(".info-text").exists()).toBe(false);
  });

  it("has no (i) on the plain fields", () => {
    const wrapper = make();
    for (const id of ["set-messages-alert_command", "set-messages-alert"]) expect(tipOf(wrapper, id), id).toBeNull();
  });

  it("shows a plain on/off setting as a checkbox that sends true or false", async () => {
    const config = configValues();
    const send = vi.fn(() => true);
    const wrapper = mount(SettingsForm, { props: { config, lastError: null, send } });
    const box = wrapper.find<HTMLInputElement>("#set-messages-alert");
    expect(box.attributes("type")).toBe("checkbox");
    expect(box.element.checked).toBe(true);
    await box.setValue(false);
    await wrapper.find("form").trigger("submit");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "messages/alert": "false" } });
  });
});
