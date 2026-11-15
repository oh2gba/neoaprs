// The Radio group and the Digipeater group of the Settings tab with any number of radios (plan sections 6 and 6a): a box for each radio that is not removed, its Enable, its Name and Remove while the station has several
// radios, its status and behind the arrow its type, its fields and what its type can do, each sent by its own radio's id; the main radio after the last box while more than one radio is on; Add radio last; one Digipeater Enable for each radio that may repeat.
// A station of six radios with the page set for a phone (375 px; jsdom has no layout, so what fits is the browser's to show), and a station whose database has radio 1 alone. The pages of the FM and HF radios of before
// are held by SettingsRadio.test.ts, SettingsRadioFold.test.ts and the tests of the form.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import SettingsForm from "@/components/SettingsForm.vue";
import { refusedAtField } from "@/lib/settinglinks";
import { useFindRadio } from "@/composables/useFindRadio";
import { setLocale } from "@/i18n";
import type { PortsMessage, RadioRow, RadioSearchMessage } from "@/protocol/protocol";
import { shallowRef } from "vue";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, hfState, portRow, radioRow, radiosTopic, status, toastOf, tncState } from "@/test/fixtures";
import { t } from "@/i18n";

const STYLES = join(dirname(fileURLToPath(import.meta.url)), "..", "styles", "settings.css");

const ports: PortsMessage = { type: "ports", sound_cards: [], keying: "", search: true, find: true, ports: [portRow("/dev/ttyUSB0", "FT232R USB UART")] };

/** The six radios of the station: the FM and HF radios of before (1, 2), a KISS TNC called Mobile (3), a Dummy HF radio called 20 m (4), a KISS TNC over TCP (5, the third FM radio by its number) and a Mercury modem
 * whose name is eight wide letters (6). */
function sixRadios(extra: Partial<Record<number, Partial<RadioRow>>> = {}): Map<string, RadioRow> {
  return radiosTopic(
    radioRow(1, "kenwood-tnc2", extra[1]),
    radioRow(2, "mercury", { number: 1, ...extra[2] }),
    radioRow(3, "kiss", { name: "Mobile", number: 2, ...extra[3] }),
    radioRow(4, "dummy-hf", { name: "20 m", number: 2, ...extra[4] }),
    radioRow(5, "kiss-tcp", { number: 3, ...extra[5] }),
    radioRow(6, "mercury", { name: "WWWWWWWW", number: 3, ...extra[6] }),
  );
}

/** The settings of a station of six radios: those of before for radios 1 and 2, the others' own in `radio_values`. */
function sixSettings(values: Record<string, string> = {}, more: Record<string, string> = {}) {
  const config = configValues({ "hf/enabled": "true", "mercury/sound_card": "plughw:1,0", ...values });
  const own = {
    "radio/3/port": "/dev/ttyACM0",
    "radio/3/baud": "",
    "radio/3/beacon": "true",
    "radio/3/path": "",
    "radio/3/digipeat": "false",
    "radio/4/beacon": "true",
    "radio/5/port": "",
    "radio/5/tcp_host": "192.168.1.5",
    "radio/5/tcp_port": "8001",
    "radio/5/beacon": "true",
    "radio/5/path": "",
    "radio/5/digipeat": "true",
    "radio/6/sound_card": "plughw:2,0",
    "radio/6/keying": "vox",
    "radio/6/tx_gain_db": "-3",
    "radio/6/beacon": "true",
    ...more,
  };
  return { ...config, radio_values: { ...config.radio_values, ...own }, radio_defaults: { ...config.radio_defaults, ...own, "radio/3/baud": "9600" } };
}

function make(more: Given = {}, values: Record<string, string> = {}) {
  const daemon = fakeDaemon({
    config: sixSettings(values),
    radios: sixRadios(),
    tnc: tncState(),
    hf: hfState(),
    ports,
    status: status({ main_radio: 1 }),
    ...more,
  });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon), attachTo: document.body });
  const group = () => {
    const found = wrapper.findAll("form > fieldset").find((f) => f.find("legend").text() === "Radio");
    if (!found) throw new Error("no Radio group");
    return found;
  };
  const box = (legend: string) => {
    const found = group()
      .findAll("fieldset.subbox")
      .find((f) => f.find("legend").text() === legend);
    if (!found) throw new Error(`no box ${legend}`);
    return found;
  };
  return { wrapper, daemon, send: daemon.send, group, box };
}

const LEGENDS = ["FM radio", "HF radio", "Mobile", "20 m", "FM radio 3", "WWWWWWWW"];

beforeEach(() => {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
  document.documentElement.classList.add("size-phone");
});
afterEach(() => {
  document.body.innerHTML = "";
  document.documentElement.classList.remove("size-phone");
  localStorage.clear();
});

describe("the Radio group of a station of six radios", () => {
  it("has RX only, then a box for each radio in the daemon's order, then the main radio, then Add radio", () => {
    const { group } = make();
    const rows = [...group().element.querySelector(".group-body")!.children];
    expect(rows[0]?.querySelector("label")?.textContent).toBe("RX only");
    expect(rows.slice(1, -2).map((row) => (row.matches("fieldset.subbox") ? row.querySelector("legend")?.textContent : "")?.trim())).toEqual(LEGENDS);
    expect(rows.at(-2)?.querySelector("label")?.textContent).toBe("Main radio");
    expect(rows.at(-2)?.contains(document.getElementById("set-station-main_radio"))).toBe(true);
    expect(rows.at(-1)?.querySelector("label")?.textContent).toBe("Add radio");
  });

  it("has in each box its Enable first, then its Name with Remove, then its status, and the Name's placeholder is what the radio is called without one", () => {
    const { box } = make();
    for (const [legend, id, placeholder] of [
      ["FM radio", 1, "FM"],
      ["Mobile", 3, "FM 2"],
      ["20 m", 4, "HF 2"],
      ["FM radio 3", 5, "FM 3"],
      ["WWWWWWWW", 6, "HF 3"],
    ] as const) {
      const fields = box(legend).findAll(".box-body > .field");
      expect(fields[0]?.find("label").text(), legend).toBe("Enable");
      expect(fields[0]?.find("input").attributes("type"), legend).toBe("checkbox");
      expect(fields[1]?.find("label").text(), legend).toBe("Name");
      const name = box(legend).find<HTMLInputElement>(`#set-radio-${id}-name`);
      expect(name.attributes("placeholder"), legend).toBe(placeholder);
      expect(box(legend).find(`#set-radio-${id}-remove`).text(), legend).toContain("Remove");
      expect(fields[1]?.element.nextElementSibling?.matches("details.radiostatus"), legend).toBe(true);
    }
    expect(box("WWWWWWWW").find<HTMLInputElement>("#set-radio-6-name").element.value).toBe("WWWWWWWW");
  });

  it("folds each box by its own arrow, kept in this browser by the radio's id, the boxes of before by their kind as they always were", async () => {
    const { box } = make();
    await box("Mobile").find("legend button.groupfold").trigger("click");
    expect(localStorage.getItem("NeoAPRS.settings.fold.radio-3")).toBe("folded");
    expect(box("Mobile").find(".box-body").attributes("style")).toContain("display: none");
    expect(box("FM radio 3").find(".box-body").attributes("style") ?? "").not.toContain("display: none");
    await box("FM radio").find("legend button.groupfold").trigger("click");
    expect(localStorage.getItem("NeoAPRS.settings.fold.fm")).toBe("folded");
  });

  it("gives every element of every box an id of its own, the radios' own carrying the radio's id", () => {
    const { group } = make();
    const ids = group()
      .findAll("[id]")
      .map((e) => e.attributes("id") ?? "");
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([]);
    for (const id of ["set-radio-3-enabled", "set-radio-3-type", "set-radio-3-port", "set-radio-3-baud", "set-radio-3-find", "settings-box-radio-3"])
      expect(ids, id).toContain(id);
    for (const id of [
      "set-radio-5-tcp_host",
      "set-radio-5-tcp_port",
      "set-radio-6-sound_card",
      "set-radio-6-keying",
      "set-radio-6-tune",
      "set-radio-6-txlevel-up",
    ])
      expect(ids, id).toContain(id);
    expect(ids).not.toContain("set-radio-5-port"); // (a TNC over TCP has its host and port, not a serial port)
    expect(ids).not.toContain("set-radio-4-tune"); // (the Dummy HF radio has no modem to tune)
  });

  it("has the main radio as a choice of the radios that are on, by name, showing the one in force, and sends the one chosen as any setting", async () => {
    const { group, send } = make();
    const select = group().find<HTMLSelectElement>("#set-station-main_radio");
    expect([...select.element.options].map((o) => o.text)).toEqual(["FM", "HF", "Mobile", "20 m", "FM 3", "WWWWWWWW"]);
    expect(select.element.value).toBe("1");
    await select.setValue("3");
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "station/main_radio": "3" } });
  });

  it("shows the main radio the setting names while that radio is on, and the one in force while it names one that is off", () => {
    const on = make({ config: { ...sixSettings(), radio_values: { ...sixSettings().radio_values, "station/main_radio": "3" } } });
    expect(on.group().find<HTMLSelectElement>("#set-station-main_radio").element.value).toBe("3");
    on.wrapper.unmount();
    const off = make({
      config: { ...sixSettings(), radio_values: { ...sixSettings().radio_values, "station/main_radio": "3" } },
      radios: sixRadios({ 3: { enabled: false, state: "stopped" } }),
      status: status({ main_radio: 2 }),
    });
    expect(off.group().find<HTMLSelectElement>("#set-station-main_radio").element.value).toBe("2");
  });

  it("has the rules of settings.css that keep a Name of eight letters whole, wrap Remove and Add under their field where the row is narrow, and never cut a legend", () => {
    const css = readFileSync(STYLES, "utf-8");
    expect(css).toMatch(/\.radioname \.field-control,\s*\.radioadd \.field-control \{\s*flex-wrap: wrap;\s*\}/);
    expect(css).toMatch(/\.radioname \.field-control \.input \{\s*flex: 1 1 9em;\s*\}/);
    expect(css).not.toMatch(/\.subbox legend[^{]*\{[^}]*(text-overflow|white-space: nowrap|overflow: hidden)/);
    const { box } = make();
    expect(box("WWWWWWWW").find("legend").text()).toBe("WWWWWWWW");
    expect(box("WWWWWWWW").find(".radioname").exists()).toBe(true);
  });
});

describe("a radio other than those of before, in its box", () => {
  it("sends its Enable, its type and its name by radio_change with its id, and its fields by set_config under its own keys", async () => {
    const { box, send } = make();
    const type = box("Mobile").find<HTMLSelectElement>("#set-radio-3-type");
    expect([...type.element.options].map((o) => o.value)).toEqual(["kenwood-tnc2", "kenwood-d710", "kantronics", "kiss", "kiss-tcp", "dummy"]);
    expect(type.element.value).toBe("kiss");
    await type.setValue("kantronics");
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_change", radio: 3, type: "kantronics" });
    const speed = box("Mobile").find<HTMLInputElement>("#set-radio-3-baud");
    expect(speed.attributes("placeholder")).toBe("9600");
    await speed.setValue("19200");
    await speed.trigger("keydown", { key: "Enter" });
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/baud": "19200" } });
    const name = box("Mobile").find<HTMLInputElement>("#set-radio-3-name");
    await name.setValue("Car");
    await name.trigger("keydown", { key: "Enter" });
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_change", radio: 3, name: "Car" });
    await box("Mobile").find("#set-radio-3-enabled").setValue(false);
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_change", radio: 3, enabled: false });
    expect(box("Mobile").find("details.radiostatus").exists()).toBe(false); // (off at once, while the daemon tells it back)
  });

  it("checks a radio's own number as the same field of before is checked, and sends the host and the port of a TNC over TCP together", async () => {
    const { box, send } = make();
    const speed = box("Mobile").find<HTMLInputElement>("#set-radio-3-baud");
    await speed.setValue("12");
    await speed.trigger("keydown", { key: "Enter" });
    expect(box("Mobile").find("#set-radio-3-baud-error").text()).toBe("300 to 921600");
    send.mockClear();
    const host = box("FM radio 3").find<HTMLInputElement>("#set-radio-5-tcp_host");
    await host.setValue("192.168.1.6");
    await host.trigger("blur", { relatedTarget: box("FM radio 3").find("#set-radio-5-tcp_port").element });
    expect(send).not.toHaveBeenCalled(); // (focus went to the other of the pair)
    await host.trigger("keydown", { key: "Enter" });
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/5/tcp_host": "192.168.1.6" } });
  });

  it("says the daemon's refusal of a change of the radio under the field it was about, and in no toast", async () => {
    const { box, daemon } = make();
    const name = box("Mobile").find<HTMLInputElement>("#set-radio-3-name");
    await name.setValue("Car");
    await name.trigger("keydown", { key: "Enter" });
    await tell(daemon, { lastError: toastOf("radio_change: the name 'Car' is another radio's already", "radio.name_taken", { name: "Car", radio: 3 }) });
    expect(box("Mobile").find("#set-radio-3-name-error").text()).toBe("the name 'Car' is another radio's already: give this one another");
    expect(refusedAtField(daemon.lastError.value)).toBe(true);
  });

  it("puts a refusal under the box that asked last, not under every box with a change on its way", async () => {
    const { box, daemon } = make();
    for (const [legend, id, text] of [
      ["Mobile", 3, "Car"],
      ["FM radio 3", 5, "Bike"],
    ] as const) {
      const name = box(legend).find<HTMLInputElement>(`#set-radio-${id}-name`);
      await name.setValue(text);
      await name.trigger("keydown", { key: "Enter" });
    }
    await tell(daemon, { lastError: toastOf("radio_change: the name 'Bike' is another radio's already", "radio.name_taken", { name: "Bike", radio: 4 }) });
    expect(box("FM radio 3").find("#set-radio-5-name-error").text()).toBe("the name 'Bike' is another radio's already: give this one another");
    expect(box("Mobile").find("#set-radio-3-name-error").exists()).toBe(false);
  });

  it("refuses itself a name another radio is called by, its name or its label, in the daemon's words, and sends nothing", async () => {
    const { box, send } = make();
    const name = box("Mobile").find<HTMLInputElement>("#set-radio-3-name");
    for (const text of ["FM", "fm 3", "20 M"]) {
      await name.setValue(text);
      await name.trigger("keydown", { key: "Enter" });
      expect(box("Mobile").find("#set-radio-3-name-error").text(), text).toBe(`the name '${text}' is another radio's already: give this one another`);
    }
    for (const text of ["FM 2", "hf 7", "RF"]) {
      await name.setValue(text); // (no other radio's now, but in the form of a label: the daemon refuses it so, radio.name_label)
      await name.trigger("keydown", { key: "Enter" });
      expect(box("Mobile").find("#set-radio-3-name-error").text(), text).toBe(
        `the name '${text}' is how a radio without a name of its own is called: give this one another`,
      );
    }
    expect(send).not.toHaveBeenCalledWith(expect.objectContaining({ cmd: "radio_change" }));
    await name.setValue("Shack");
    await name.trigger("keydown", { key: "Enter" });
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_change", radio: 3, name: "Shack" });
  });

  it("refuses a name in the form of a label in the page's language too, as the daemon refuses its English ones", async () => {
    const { wrapper, send } = make();
    setLocale("de");
    try {
      const name = wrapper.find<HTMLInputElement>("#set-radio-3-name");
      await name.setValue("KW 4");
      await name.trigger("keydown", { key: "Enter" });
      expect(wrapper.find("#set-radio-3-name-error").text()).toContain("KW 4");
      expect(send).not.toHaveBeenCalledWith(expect.objectContaining({ cmd: "radio_change" }));
    } finally {
      setLocale("en");
    }
  });

  it("keeps the type chosen while its row changes for anything else, and says the refusal that comes after under the type", async () => {
    const { box, daemon } = make();
    const type = () => box("Mobile").find<HTMLSelectElement>("#set-radio-3-type");
    await type().setValue("kiss-tcp");
    expect(box("Mobile").find("#set-radio-3-tcp_host").exists()).toBe(true);
    await tell(daemon, { radios: sixRadios({ 3: { state: "connecting" } }) });
    expect(type().element.value).toBe("kiss-tcp");
    expect(box("Mobile").find("#set-radio-3-tcp_host").exists()).toBe(true);
    await tell(daemon, { lastError: toastOf("radio_change: that device is in use by HF", "radio.resource_held", { resource: "serial", holder: "HF" }) });
    expect(box("Mobile").find("#set-radio-3-type-error").text()).not.toBe("");
    expect(refusedAtField(daemon.lastError.value)).toBe(true);
    expect(type().element.value).toBe("kiss"); // (refused: the daemon's again)
  });

  it("shows the daemon's type again once its row says the type asked", async () => {
    const { box, daemon } = make();
    await box("Mobile").find<HTMLSelectElement>("#set-radio-3-type").setValue("kantronics");
    await tell(daemon, { radios: sixRadios({ 3: { type: "kantronics" } }) });
    await tell(daemon, { radios: sixRadios({ 3: { type: "kiss" } }) }); // (changed again elsewhere: the row is what is shown)
    expect(box("Mobile").find<HTMLSelectElement>("#set-radio-3-type").element.value).toBe("kiss");
  });

  it("opens its box for a refusal of a change of it", async () => {
    localStorage.setItem("NeoAPRS.settings.fold.radio-3", "folded");
    const { box, daemon } = make();
    expect(box("Mobile").find(".box-body").attributes("style")).toContain("display: none");
    await box("Mobile").find<HTMLSelectElement>("#set-radio-3-type").setValue("kantronics");
    await tell(daemon, { lastError: toastOf("radio_change: the radio could not be stored; nothing changed", "setting.not_stored") });
    expect(box("Mobile").find(".box-body").attributes("style") ?? "").not.toContain("display: none");
  });

  it("does not say radio 1's found port beside another radio's automatic port", () => {
    const { box } = make({ config: sixSettings({ "serial/port": "", "serial/last_port": "/dev/ttyUSB0" }, { "radio/3/port": "" }) });
    expect(box("FM radio").find(".port-found").exists()).toBe(true);
    expect(box("Mobile").find("#set-radio-3-port").exists()).toBe(true);
    expect(box("Mobile").find(".port-found").exists()).toBe(false);
  });

  it("checks a name of more than eight letters itself, with the daemon's words, and puts the name back with Esc", async () => {
    const { box, send } = make();
    const name = box("Mobile").find<HTMLInputElement>("#set-radio-3-name");
    await name.setValue("Mobile123");
    await name.trigger("keydown", { key: "Enter" });
    expect(box("Mobile").find("#set-radio-3-name-error").text()).toBe(
      "the name 'Mobile123' cannot be a radio's: a name is at most 8 printable ASCII characters (letters, digits and the signs of the keyboard)",
    );
    expect(send).not.toHaveBeenCalledWith(expect.objectContaining({ cmd: "radio_change" }));
    await name.trigger("keydown", { key: "Escape" });
    expect(name.element.value).toBe("Mobile");
    expect(box("Mobile").find("#set-radio-3-name-error").exists()).toBe(false);
  });

  it("is removed by Remove pressed twice, in the room of the longer word", async () => {
    const { box, send } = make();
    const remove = box("Mobile").find("#set-radio-3-remove");
    expect(remove.findAll(".twowords > span").map((s) => s.text())).toEqual(["Remove", "Really remove?"]);
    await remove.trigger("click");
    expect(send).not.toHaveBeenCalledWith({ cmd: "radio_remove", radio: 3 });
    expect(remove.find(".twowords > span:not(.twowords-off)").text()).toBe("Really remove?");
    await remove.trigger("click");
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_remove", radio: 3 });
  });

  it("asks for its own ports, finds itself, and tunes and keys its own modem", async () => {
    const searches = shallowRef<RadioSearchMessage | null>(null);
    const daemon = fakeDaemon({ config: sixSettings(), radios: sixRadios(), tnc: tncState(), hf: hfState(), ports, status: status({ main_radio: 1 }) });
    const find = useFindRadio(searches, daemon.lastError, shallowRef("open"), daemon.send, daemon.settings, daemon.config, daemon.say);
    const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon({ ...daemon, findRadio: find }), attachTo: document.body });
    await wrapper.find("#set-radio-6-txlevel-up").trigger("click");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/6/tx_gain_db": "-2" } });
    await tell(daemon, { config: sixSettings({}, { "radio/6/tx_gain_db": "-2" }) });
    const refresh = wrapper.findAll("button").find((b) => b.text() === "Refresh" && b.element.closest(".field")?.querySelector("#set-radio-3-port"));
    await refresh?.trigger("click");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "list_ports", radio: 3 });
    await wrapper.find("#set-radio-3-find").trigger("click");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "find_radio", radio: 3 });
    expect(find.text.value).toBe("Mobile: Looking for the radio…");
    expect(wrapper.find<HTMLButtonElement>("#find-radio").element.disabled).toBe(true); // (one search at a time: the other boxes' buttons wait)
    searches.value = {
      type: "radio_search",
      state: "found",
      port: "/dev/ttyUSB0",
      baud: 9600,
      profile: "kiss",
      number: 0,
      total: 0,
      radio: 3,
      radio_type: "kiss",
    };
    await flushPromises();
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/port": "/dev/ttyUSB0", "radio/3/baud": "9600" } });
    await wrapper.find("#set-radio-6-tune").trigger("click");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "radio_tune", radio: 6, on: true });
    await wrapper.find("#set-radio-6-keying-test").trigger("click");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "radio_key_test", radio: 6 });
  });

  it("shows its line from its row: connected with its last packet, not connected in the coded problem's words, the Dummy's muted line", () => {
    const { box } = make({
      radios: sixRadios({
        5: { state: "waiting", problem: { code: "radio.not_connected", params: { name: "FM 3" } } },
        4: { state: "connected", dummy: true },
      }),
    });
    expect(box("Mobile").find(".tncstatus").text()).toBe("Last packet 30 s ago");
    expect(box("Mobile").find<HTMLDetailsElement>("details.radiostatus").element.open).toBe(false);
    expect(box("FM radio 3").find(".tncstatus").text()).toBe("Not connected");
    expect(box("FM radio 3").find<HTMLDetailsElement>("details.radiostatus").element.open).toBe(true);
    expect(box("20 m").find(".statetext").text()).toBe("Dummy");
    expect(box("20 m").find(".tncstatus").text()).toBe("Dummy HF radio: made-up distant stations, your frames on the speakers, nothing goes on the air");
  });
});

describe("a radio that is off, removed or the only one on", () => {
  it("is, while it is off, its Enable and its Name with Remove, and no status; ticking it sends its Enable", async () => {
    const { box, send } = make({ radios: sixRadios({ 3: { enabled: false, state: "stopped" } }) });
    expect(box("Mobile").find("details.radiostatus").exists()).toBe(false);
    expect(box("Mobile").find("#set-radio-3-name").exists()).toBe(true);
    expect(box("Mobile").find<HTMLInputElement>("#set-radio-3-enabled").element.checked).toBe(false);
    await box("Mobile").find("#set-radio-3-enabled").setValue(true);
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_change", radio: 3, enabled: true });
  });

  it("turns the Remove of the last radio on off as soon as the other is unticked, before the daemon tells it", async () => {
    const off = { enabled: false, state: "stopped" } as const;
    const { box } = make({ radios: sixRadios({ 2: off, 4: off, 5: off, 6: off }) }, { "hf/enabled": "false" });
    expect(box("Mobile").find<HTMLButtonElement>("#set-radio-3-remove").element.disabled).toBe(false);
    await box("FM radio").find("#set-fm-enabled").setValue(false);
    expect(box("Mobile").find<HTMLButtonElement>("#set-radio-3-remove").element.disabled).toBe(true);
    expect(box("Mobile").find<HTMLInputElement>("#set-radio-3-enabled").element.disabled).toBe(true);
  });

  it("has no box once it is removed, and the others keep theirs", () => {
    const { group } = make({ radios: sixRadios({ 6: { removed: true, enabled: false, state: "stopped" } }) });
    expect(
      group()
        .findAll("fieldset.subbox > legend")
        .map((l) => l.text()),
    ).toEqual(LEGENDS.slice(0, 5));
  });

  it("greys the Enable of the only radio on and turns its Remove off; with one radio on there is no main radio, and every box keeps its Name", () => {
    // (plan section 6: Name and Remove "outside the status fold, so that a radio that is off can be renamed and removed"; decision 4: the main radio "shown only with several radios", several on)
    const off = { enabled: false, state: "stopped" } as const;
    const { group, box } = make({ radios: sixRadios({ 2: off, 3: off, 4: off, 5: off, 6: off }) }, { "hf/enabled": "false" });
    expect(group().find("#set-station-main_radio").exists()).toBe(false);
    expect(group().text()).not.toContain("Main radio");
    expect(group().find<HTMLInputElement>("#set-radio-3-name").exists()).toBe(true);
    expect(group().find<HTMLButtonElement>("#set-radio-3-remove").element.disabled).toBe(false);
    expect(group().find<HTMLButtonElement>("#set-radio-1-remove").element.disabled).toBe(true);
    expect(box("FM radio").find<HTMLInputElement>("#set-fm-enabled").element.disabled).toBe(true);
    expect(box("Mobile").find<HTMLInputElement>("#set-radio-3-enabled").element.disabled).toBe(false);
  });

  it("turns the other's Enable and Remove off at once when one of two radios other than those of before is unticked", async () => {
    const off = { enabled: false, state: "stopped" } as const;
    const { box } = make({ radios: sixRadios({ 1: off, 2: off, 4: off, 6: off }) }, { "fm/enabled": "false", "hf/enabled": "false" });
    expect(box("Mobile").find<HTMLInputElement>("#set-radio-3-enabled").element.disabled).toBe(false);
    await box("FM radio 3").find("#set-radio-5-enabled").setValue(false);
    expect(box("Mobile").find<HTMLInputElement>("#set-radio-3-enabled").element.disabled).toBe(true);
    expect(box("Mobile").find<HTMLButtonElement>("#set-radio-3-remove").element.disabled).toBe(true);
  });

  it("asks for the sound cards of a Mercury radio other than radio 2 when it is ticked", async () => {
    const off = { enabled: false, state: "stopped" } as const;
    const { daemon } = make({ radios: sixRadios({ 6: off }) });
    expect(daemon.send).not.toHaveBeenCalledWith({ cmd: "list_ports", radio: 6 });
    await tell(daemon, { radios: sixRadios() });
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "list_ports", radio: 6 });
    expect(daemon.send).not.toHaveBeenCalledWith({ cmd: "list_ports", radio: 4 }); // (the Dummy HF radio has no sound card)
  });

  it("greys the only radio on when it is not one of before", () => {
    const off = { enabled: false, state: "stopped" } as const;
    const { box } = make({ radios: sixRadios({ 1: off, 2: off, 4: off, 5: off, 6: off }) }, { "fm/enabled": "false", "hf/enabled": "false" });
    expect(box("Mobile").find<HTMLInputElement>("#set-radio-3-enabled").element.disabled).toBe(true);
    expect(box("Mobile").find(".field").attributes("title")).toBe("The station's only radio that is on");
  });
});

describe("Add radio", () => {
  it("offers every type from the one list, adds nothing when a type is chosen, adds it with Add, and is ready for the next", async () => {
    const { group, send } = make();
    const select = () => group().find<HTMLSelectElement>("#set-radio-add");
    const add = () => group().find<HTMLButtonElement>("#set-radio-add-button");
    expect([...select().element.options].map((o) => o.text)).toEqual([
      "Radio type",
      "Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2",
      "Kenwood TM-D710 / TH-D72",
      "Kantronics KPC-3+",
      "KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)",
      "KISS over TCP (Direwolf, soundmodem)",
      "Dummy (no radio, made-up traffic)",
      "Mercury HF modem (sound card, SSB radio)",
      "Dummy HF radio (no radio, made-up distant stations)",
    ]);
    expect([add().text(), add().element.disabled]).toEqual(["Add", true]);
    for (const type of ["kiss", "kiss-tcp", "dummy-hf"]) await select().setValue(type); // (as the arrow keys of a closed list choose each line they pass)
    expect(send).not.toHaveBeenCalledWith(expect.objectContaining({ cmd: "radio_add" }));
    expect(add().element.disabled).toBe(false);
    await add().trigger("click");
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_add", type: "dummy-hf" });
    expect(send.mock.calls.filter(([command]) => command.cmd === "radio_add")).toHaveLength(1);
    expect([select().element.value, add().element.disabled]).toEqual(["", true]);
  });

  it("has the one (i) of the Radio type, of the one list", async () => {
    const { group } = make();
    const row = group().find("#set-radio-add").element.closest(".field")!;
    expect(row.querySelectorAll(".info-toggle")).toHaveLength(1);
    expect(row.querySelector(".info-toggle")?.getAttribute("aria-label")).toBe(t("settings.profile.tip_label"));
    (row.querySelector(".info-toggle") as HTMLElement).click();
    await flushPromises();
    expect([...row.querySelectorAll(".info-line")].map((l) => l.textContent)).toEqual([t("settings.profile.tip1"), t("settings.profile.tip2")]);
  });

  it("gives the Radio type of every box, FM or HF, the same one (i) as Add radio's, of the whole list, with no file of the documents in it (plan section 6: one (i) for the one list)", async () => {
    const { group } = make();
    const tips: string[][] = [];
    for (const id of ["set-tnc-profile", "set-hf-profile", "set-radio-3-type", "set-radio-4-type", "set-radio-6-type", "set-radio-add"]) {
      const row = group().find(`#${id}`).element.closest(".field")!;
      const toggle = row.querySelector<HTMLElement>(".info-toggle")!;
      toggle.click();
      await flushPromises();
      tips.push([id, toggle.getAttribute("aria-label") ?? "", ...[...row.querySelectorAll(".info-line")].map((l) => l.textContent ?? "")]);
    }
    const one = [t("settings.profile.tip_label"), t("settings.profile.tip1"), t("settings.profile.tip2")];
    expect(tips.map(([, ...tip]) => tip)).toEqual(tips.map(() => one));
    expect(one.join(" ")).not.toMatch(/docs\/|\.md\b/);
    expect(one.join(" ")).toContain("Mercury");
  });

  it("leads to the box of the radio added once its row has come, once: it opens and its Enable takes the keyboard, and folded it opens again only for what a box opens for", async () => {
    const { daemon, box, wrapper } = make();
    localStorage.setItem("NeoAPRS.settings.fold.radio-7", "folded");
    await wrapper.find("#set-radio-add").setValue("dummy-hf");
    await wrapper.find("#set-radio-add-button").trigger("click");
    await tell(daemon, { radioAdded: { type: "radio_added", id: 7 } });
    const topic = (extra: Partial<RadioRow> = {}) => {
      const made = sixRadios();
      made.set("7", radioRow(7, "dummy-hf", { number: 3, ...extra }));
      return made;
    };
    await tell(daemon, { radios: topic() });
    await flushPromises();
    const body = () => box("HF radio 3").find(".box-body").attributes("style") ?? "";
    expect(body()).not.toContain("display: none");
    expect(document.activeElement?.id).toBe("set-radio-7-enabled");
    await box("HF radio 3").find("legend button.groupfold").trigger("click");
    await tell(daemon, { radios: topic({ stats: { ...tncState().stats, packets: 3 } }) });
    expect(body()).toContain("display: none"); // (the operator folded it: a new row does not open it again)
    await tell(daemon, { radios: topic({ state: "waiting", problem: { code: "radio.not_connected", params: { name: "HF 3" } } }) });
    expect(body()).not.toContain("display: none");
  });
});

describe("the Digipeater group of a station of several radios that may repeat", () => {
  const digi = (wrapper: ReturnType<typeof make>["wrapper"]) => wrapper.findAll("form > fieldset").find((f) => f.find("legend").text() === "Digipeater");

  it("has an Enable for each radio that may repeat and is on, each in a box with the radio's legend, with its own counts", () => {
    const counted = { stats: { ...tncState().stats, digipeated: 4, digipeated_at: new Date(Date.parse("2026-10-21T12:00:00Z") - 120_000).toISOString() } };
    const { wrapper } = make({ radios: sixRadios({ 5: counted }) }, { "digi/enabled": "true" });
    const group = digi(wrapper);
    expect(group?.findAll("fieldset.subbox > legend").map((l) => l.text())).toEqual(["FM radio", "Mobile", "FM radio 3"]);
    expect(group?.findAll("input[type=checkbox]").map((i) => i.attributes("id"))).toEqual(["set-digi-enabled", "set-radio-3-digipeat", "set-radio-5-digipeat"]);
    const third = group?.findAll("fieldset.subbox").find((b) => b.find("legend").text() === "FM radio 3");
    expect(third?.find(".tncstatus").text()).toBe("4 packets repeated · last 2 min ago");
    const mobile = group?.findAll("fieldset.subbox").find((b) => b.find("legend").text() === "Mobile");
    expect(mobile?.find(".statusfold").exists()).toBe(false); // (its digipeater is off)
  });

  it("sends a radio's own Enable as its setting", async () => {
    const { wrapper, send } = make();
    await wrapper.find("#set-radio-3-digipeat").setValue(true);
    expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/digipeat": "true" } });
  });

  it("says the radio of its one Enable while several radios are on, and is the one plain Enable while that radio is the only one on", () => {
    // (plan section 6: "one Digipeater Enable (with its own counts) for each radio that may repeat ..., each row with the radio's name when there are several")
    const off = { enabled: false, state: "stopped" } as const;
    const several = make({ radios: sixRadios({ 1: off, 5: off }) }, { "fm/enabled": "false" });
    expect(
      digi(several.wrapper)
        ?.findAll("fieldset.subbox > legend")
        .map((l) => l.text()),
    ).toEqual(["Mobile"]);
    expect(
      digi(several.wrapper)
        ?.findAll("input[type=checkbox]")
        .map((i) => i.attributes("id")),
    ).toEqual(["set-radio-3-digipeat"]);
    several.wrapper.unmount();
    const alone = make({ radios: sixRadios({ 1: off, 2: off, 4: off, 5: off, 6: off }) }, { "fm/enabled": "false", "hf/enabled": "false" });
    expect(digi(alone.wrapper)?.findAll("fieldset.subbox").length).toBe(0);
    expect(
      digi(alone.wrapper)
        ?.findAll("input[type=checkbox]")
        .map((i) => i.attributes("id")),
    ).toEqual(["set-radio-3-digipeat"]);
  });
});

/** The rows of the Radio group up to its last box (RX only and the boxes): the very nodes, in their order, which ticking a radio must leave as they are. */
function rowsToLastBox(): Element[] {
  const rows = [...(document.querySelector("#set-radio-add")?.closest(".group-body")?.children ?? [])];
  const last = rows.map((row) => row.matches("fieldset.subbox")).lastIndexOf(true);
  if (last < 0) throw new Error("no box");
  return rows.slice(0, last + 1);
}

/** Whether ticking left the rows up to the last box the very same nodes in the same order. */
const sameNodes = (nodes: Element[]): boolean => {
  const now = rowsToLastBox();
  return now.length === nodes.length && now.every((row, i) => row === nodes[i]);
};

/** Where the main radio's row stands among the rows of the Radio group: right after the last box and right before Add radio, or null when it is not there. */
function mainRadioPlace(): "after the last box" | "elsewhere" | null {
  const select = document.getElementById("set-station-main_radio");
  if (select === null) return null;
  const rows = [...(select.closest(".group-body")?.children ?? [])];
  const at = rows.findIndex((row) => row.contains(select));
  const before = rows[at - 1];
  const after = rows[at + 1];
  return before?.matches("fieldset.subbox") && after?.contains(document.getElementById("set-radio-add")) ? "after the last box" : "elsewhere";
}

/** The rows (fields' labels and boxes' legends) of the Settings tab that stand before an element, by their text: what would move the element if it changed. */
function rowsBefore(id: string): string[] {
  const target = document.getElementById(id);
  if (target === null) throw new Error(`no ${id}`);
  return [...document.querySelectorAll(".settings .field > label, .settings fieldset.subbox > legend")]
    .filter((el) => el.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING)
    .map((el) => el.textContent?.trim() ?? "");
}

describe("ticking a radio moves nothing under the pointer", () => {
  it("keeps every row above the HF radio's Enable of a station of before when it is ticked and the daemon tells it", async () => {
    const daemon = fakeDaemon({ tnc: tncState(), hf: hfState(), ports, status: status({ main_radio: 1 }) });
    mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon), attachTo: document.body });
    const was = rowsBefore("set-hf-enabled");
    const nodes = rowsToLastBox();
    expect(was).not.toContain("Main radio");
    expect(was).toContain("Name");
    expect(mainRadioPlace()).toBeNull();
    const input = document.getElementById("set-hf-enabled") as HTMLInputElement;
    input.checked = true;
    input.dispatchEvent(new Event("change"));
    await flushPromises();
    expect(rowsBefore("set-hf-enabled")).toEqual(was);
    expect(sameNodes(nodes)).toBe(true);
    expect(mainRadioPlace()).toBe("after the last box");
    await tell(daemon, { config: configValues({ "hf/enabled": "true" }) });
    await flushPromises();
    expect(rowsBefore("set-hf-enabled")).toEqual(was);
    expect(sameNodes(nodes)).toBe(true);
    expect(mainRadioPlace()).toBe("after the last box");
    expect((document.getElementById("set-station-main_radio") as HTMLSelectElement).disabled).toBe(false);
  });

  it("keeps every row above radio 3's Enable when it is ticked beside radio 1 alone", async () => {
    const off = { enabled: false, state: "stopped" } as const;
    const { daemon } = make({ radios: sixRadios({ 2: off, 3: off, 4: off, 5: off, 6: off }) }, { "hf/enabled": "false" });
    const was = rowsBefore("set-radio-3-enabled");
    const nodes = rowsToLastBox();
    expect(mainRadioPlace()).toBeNull();
    (document.getElementById("set-radio-3-enabled") as HTMLInputElement).click();
    await flushPromises();
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "radio_change", radio: 3, enabled: true });
    expect(rowsBefore("set-radio-3-enabled")).toEqual(was);
    expect(sameNodes(nodes)).toBe(true);
    expect(mainRadioPlace()).toBe("after the last box");
    await tell(daemon, { radios: sixRadios({ 2: off, 4: off, 5: off, 6: off }) });
    await flushPromises();
    expect(rowsBefore("set-radio-3-enabled")).toEqual(was);
    expect(sameNodes(nodes)).toBe(true);
    expect(mainRadioPlace()).toBe("after the last box");
  });

  it("takes the main radio away, and moves nothing above it, when one of two radios on is unticked", async () => {
    const off = { enabled: false, state: "stopped" } as const;
    const { daemon } = make({ radios: sixRadios({ 2: off, 4: off, 5: off, 6: off }) }, { "hf/enabled": "false" });
    expect(mainRadioPlace()).toBe("after the last box");
    const nodes = rowsToLastBox();
    (document.getElementById("set-radio-3-enabled") as HTMLInputElement).click();
    await flushPromises();
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "radio_change", radio: 3, enabled: false });
    expect(mainRadioPlace()).toBeNull();
    expect(sameNodes(nodes)).toBe(true);
    await tell(daemon, { radios: sixRadios({ 2: off, 3: off, 4: off, 5: off, 6: off }) });
    await flushPromises();
    expect(mainRadioPlace()).toBeNull();
  });

  it("lets a radio that is off beside the one radio on be renamed and removed without ticking it", async () => {
    const off = { enabled: false, state: "stopped" } as const;
    const { box, send } = make(
      { radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(3, "kiss", { name: "Mobile", number: 2, ...off })) },
      { "hf/enabled": "false" },
    );
    const remove = box("Mobile").find<HTMLButtonElement>("#set-radio-3-remove");
    expect(remove.element.disabled).toBe(false);
    await remove.trigger("click");
    await remove.trigger("click");
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_remove", radio: 3 });
    expect(send).not.toHaveBeenCalledWith(expect.objectContaining({ cmd: "radio_change", enabled: true }));
    expect(box("Mobile").find("#set-radio-3-name").exists()).toBe(true);
  });
});

describe("a station whose database has radio 1 alone", () => {
  const one = (row: Partial<RadioRow> = {}) =>
    make({ radios: radiosTopic(radioRow(1, "kenwood-tnc2", row)), config: configValues(), status: status({ main_radio: 1 }) });

  it("sees today's box of its one radio and Add radio, and no HF box, no main radio, no Name", () => {
    const { group } = one();
    const rows = [...group().element.querySelector(".group-body")!.children];
    expect(rows[0]?.querySelector("label")?.textContent).toBe("RX only");
    expect(
      group()
        .findAll("fieldset.subbox > legend")
        .map((l) => l.text()),
    ).toEqual(["FM radio"]);
    expect(rows.at(-1)?.querySelector("label")?.textContent).toBe("Add radio");
    for (const id of ["#set-station-main_radio", "#set-radio-1-name", "#set-radio-1-remove", "#set-hf-enabled"])
      expect(group().find(id).exists(), id).toBe(false);
    expect(group().find<HTMLInputElement>("#set-fm-enabled").element.disabled).toBe(true);
    expect(group().find("#set-tnc-profile").exists()).toBe(true);
  });

  it("has today's legend for its one radio even when it was named while it had a second", () => {
    const { group } = one({ name: "Car" });
    expect(
      group()
        .findAll("fieldset.subbox > legend")
        .map((l) => l.text()),
    ).toEqual(["FM radio"]);
  });
});
