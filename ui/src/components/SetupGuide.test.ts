import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { nextTick, ref, shallowRef } from "vue";
import SettingsForm from "@/components/SettingsForm.vue";
import SetupGuide from "@/components/SetupGuide.vue";
import type { Toast } from "@/composables/useDaemon";
import { useFindRadio } from "@/composables/useFindRadio";
import { useSettings } from "@/composables/useSettings";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { SYMBOL_CHOICES } from "@/lib/setup";
import { addTypeChoices, typeChoices } from "@/lib/settingsradio";
import { RADIO_TYPES } from "@/protocol/lists";
import type {
  Command,
  ConfigValues,
  MapState,
  PortsMessage,
  RadioRow,
  RadioSearchMessage,
  SavedMessage,
} from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { configValues, mapFile, mapState, toastOf, portRow, radioRow, radioSearch, radiosTopic } from "@/test/fixtures";

const STYLES = join(dirname(fileURLToPath(import.meta.url)), "..", "styles");

const fresh = (extra: Record<string, string> = {}, radios: Record<string, string> = {}) =>
  configValues(
    { "beacon/interval_min": "0", "station/call": "", "station/lat": "", "station/lon": "", ...extra },
    { "radio/1/baud": "", "radio/1/port": "", ...radios },
  );
const row = (device: string, description: string) => portRow(device, description);
const ports = (extra: Partial<PortsMessage> = {}): PortsMessage => ({
  type: "ports",
  sound_cards: [],
  keying: "",
  search: true,
  find: true,
  ports: [row("/dev/ttyUSB0", "FT232R USB UART"), row("/dev/ttyACM0", "n/a")],
  radio: null,
  ...extra,
});
/** A station of radio 1 alone, a serial TNC. */
const oneRadio = () => radiosTopic(radioRow(1, "kenwood-tnc2"));

interface Made {
  config?: ConfigValues;
  map?: MapState | null;
  /**
   * the topic `radios`; by default radio 1 alone (test/context.ts); null while the daemon has not
   * told it
   */
  radios?: Map<string, RadioRow> | null;
  ports?: PortsMessage | null;
}

/**
 * The guide as the page makes it, with the page's settings (the queue the Settings tab has too) and
 * Find my radio over them.
 */
function make(opts: Made = {}) {
  const config = ref<ConfigValues | null>(opts.config ?? fresh());
  const lastError = ref<Toast | null>(null);
  const portList = ref<PortsMessage | null>(opts.ports ?? null);
  const sent: Command[] = [];
  const send = (command: Command) => (sent.push(command), true);
  // The saves of the guide and the settings are read without their number, which `answer` gives
  // back as `saved`.
  const saved = shallowRef<SavedMessage | null>(null);
  const out: number[] = [];
  const numbered = (command: Command): boolean => {
    if (command.cmd !== "set_config") return send(command);
    if (command.id != null) out.push(command.id);
    return send({ cmd: command.cmd, values: command.values });
  };
  const guide = useSetupGuide(config, lastError, numbered, null, undefined, saved);
  guide.show();
  const map = opts.map === undefined ? mapState() : opts.map;
  const settings = useSettings(config, lastError, numbered, { saved, connection: shallowRef("open" as const) });
  const radioSearch = shallowRef<RadioSearchMessage | null>(null);
  const findRadio = useFindRadio(
    radioSearch,
    lastError,
    shallowRef("open" as const),
    send,
    settings,
    config,
    () => undefined,
  );
  const daemon = fakeDaemon({
    config,
    lastError,
    ports: portList,
    guide,
    map,
    send,
    settings,
    findRadio,
    ...(opts.radios !== undefined ? { radios: opts.radios } : {}),
  });
  const wrapper = mount(SetupGuide, { global: withDaemon(daemon), attachTo: document.body });
  const type = (id: string, text: string) => wrapper.find<HTMLInputElement>(`#${id}`).setValue(text);
  /** A typed field of the Radio step finished with Enter, as in the Settings tab. */
  const enter = async (id: string, text: string) => {
    await type(id, text);
    await wrapper.find(`#${id}`).trigger("keydown", { key: "Enter" });
  };
  const next = () => wrapper.find("form").trigger("submit");
  const button = (label: string) => wrapper.findAll("button").find((b) => b.text() === label);
  const finish = () => wrapper.find<HTMLButtonElement>("button[type=submit]");
  const configs = () => sent.filter((c) => c.cmd === "set_config");
  /**
   * The daemon takes the last save and tells the settings again, which is its answer (the queue of
   * the settings sends the next change after it).
   */
  const answer = async () => {
    const last = configs().at(-1);
    if (last?.cmd === "set_config" && config.value) {
      const own = (radio: boolean) =>
        Object.fromEntries(Object.entries(last.values).filter(([key]) => key.startsWith("radio/") === radio));
      config.value = {
        ...config.value,
        values: { ...config.value.values, ...own(false) },
        radio_values: { ...config.value.radio_values, ...own(true) },
      };
    }
    await flushPromises();
    const id = out.shift();
    if (id !== undefined) saved.value = { type: "saved", id };
    await flushPromises();
  };
  /**
   * Fills the call and the position and stands on the step with this index (1 is the position, 3
   * the radio).
   */
  const stand = async (step: number) => {
    await type("setup-call", "oh2abc");
    await next();
    await type("setup-lat", "60.17");
    await type("setup-lon", "24.94");
    for (let i = 1; i < step; i++) await next();
    await flushPromises();
  };
  return {
    wrapper,
    guide,
    config,
    lastError,
    portList,
    radioSearch,
    sent,
    type,
    enter,
    next,
    button,
    finish,
    configs,
    answer,
    saved,
    out,
    stand,
    daemon,
  };
}

/** The boxes of the Radio step, by their legends. */
const legends = (wrapper: VueWrapper) =>
  wrapper.findAll(".setup-body fieldset.subbox:not(.pskbox) > legend").map((l) => l.text());
const boxOf = (wrapper: VueWrapper, legend: string) => {
  const found = wrapper.findAll(".setup-body fieldset.subbox").find((f) => f.find("legend").text() === legend);
  if (!found) throw new Error(`no box ${legend}`);
  return found;
};
/** The labels of the rows of the step, in their order, outside the boxes' folds included. */
const labels = (wrapper: VueWrapper) => wrapper.findAll(".setup-body .field > label").map((l) => l.text());

/** The place, sent on its own as the Position step is left (the daemon makes the map round it). */
const PLACE = { cmd: "set_config", values: { "station/lat": "60.17", "station/lon": "24.94" } };
/**
 * What Finish sends on a fresh installation that keeps the symbol: the call, the place, the beacon
 * of a new station; nothing of a radio.
 */
const FINISH = {
  cmd: "set_config",
  values: { "station/call": "OH2ABC", "station/lat": "60.17", "station/lon": "24.94", "beacon/interval_min": "30" },
};
const ONLY = "The station's only radio that is on";

afterEach(() => {
  document.body.replaceChildren();
  document.documentElement.classList.remove("size-phone");
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("SetupGuide: the frame", () => {
  it("is a panel with a heading per step and no explanation: four steps in the indicator, the step's title, Next", () => {
    const { wrapper } = make();
    expect(wrapper.find("[role='dialog']").attributes("aria-label")).toBe("Setup");
    expect(wrapper.findAll(".setup-dot").map((b) => b.attributes("title"))).toEqual([
      "Call",
      "Position",
      "Symbol",
      "Radio",
    ]);
    expect(wrapper.find(".setup-dot.active").text()).toBe("1");
    // the steps ahead have answers already, but are not done
    expect(wrapper.findAll(".setup-dot.done")).toHaveLength(0);
    expect(wrapper.find(".setup-step-name").text()).toBe("Call");
    expect(wrapper.findAll(".setup-step-name")).toHaveLength(1);
    expect(wrapper.find("button[type=submit]").text()).toBe("Next");
    expect(wrapper.find("p").exists()).toBe(false);
    expect(wrapper.find(".setup-foot button").text()).toBe("Next"); // no Back on the first step
  });

  it("is nothing while closed", async () => {
    const { wrapper, guide, stand } = make();
    await stand(1);
    guide.close();
    await nextTick();
    expect(wrapper.find(".setup").exists()).toBe(false);
  });

  it("sets the beacon of a new station to every 30 min with Finish, without a word about it, and leaves the beacon of a station that has a call alone", async () => {
    const { wrapper, guide, stand } = make();
    await stand(3);
    expect(wrapper.text().toLowerCase()).not.toContain("beacon");
    expect(guide.changes["beacon/interval_min"]).toBe("30");
    const again = make({ config: configValues({ "beacon/interval_min": "0" }) });
    expect(again.guide.changes["beacon/interval_min"]).toBeUndefined();
  });

  it("closes with the cross and with Escape, and its answers are there when it is opened again", async () => {
    const { wrapper, guide, type } = make();
    await type("setup-call", "oh2abc");
    await wrapper.find(".setup-close").trigger("click");
    expect(guide.open).toBe(false);
    guide.show();
    await nextTick();
    expect(wrapper.find<HTMLInputElement>("#setup-call").element.value).toBe("OH2ABC");
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await nextTick();
    expect(guide.open).toBe(false);
    expect(wrapper.find(".setup").exists()).toBe(false);
  });

  it("ignores Escape while it is closed", () => {
    const { guide } = make();
    guide.close();
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(guide.open).toBe(false);
  });

  it("puts the cursor in the first field when it opens and when the step changes", async () => {
    const { wrapper, guide, stand } = make();
    await flushPromises();
    expect(document.activeElement).toBe(wrapper.find("#setup-call").element);
    await stand(1);
    await flushPromises();
    expect(guide.step).toBe(1);
    expect(document.activeElement).toBe(wrapper.find("#setup-lat").element);
  });

  it("goes back with Back and the indicator, and forward over a step with its answers only", async () => {
    const { wrapper, guide, stand, button } = make();
    await wrapper.findAll(".setup-dot")[3]?.trigger("click");
    expect(guide.step).toBe(0);
    await stand(2);
    expect(guide.step).toBe(2);
    await button("Back")?.trigger("click");
    expect(guide.step).toBe(1);
    await wrapper.findAll(".setup-dot")[0]?.trigger("click");
    expect(wrapper.find(".setup-step-name").text()).toBe("Call");
    expect(wrapper.findAll(".setup-dot")[1]?.classes()).toContain("done");
    await wrapper.findAll(".setup-dot")[3]?.trigger("click");
    expect(wrapper.find(".setup-step-name").text()).toBe("Radio");
    expect(wrapper.find(".setup-dot.active").attributes("aria-current")).toBe("step");
  });
});

describe("SetupGuide: the call", () => {
  it("is checked as it is typed, the daemon's rules, and Next waits", async () => {
    const { wrapper, type, next, guide } = make();
    const nextButton = () => wrapper.find("button[type=submit]");
    expect(nextButton().attributes("disabled")).toBeDefined();
    await type("setup-call", "n0call");
    expect(wrapper.find(".field-error").text()).toBe("N0CALL is not a call");
    expect(wrapper.find("#setup-call").attributes("aria-invalid")).toBe("true");
    expect(nextButton().attributes("disabled")).toBeDefined();
    await next();
    expect(guide.step).toBe(0);
    await type("setup-call", "ab");
    expect(wrapper.find(".field-error").text()).toBe("Not a call");
    await type("setup-call", "oh2abc-9");
    expect(wrapper.find(".field-error").exists()).toBe(false);
    expect(guide.fields.call).toBe("OH2ABC-9");
    expect(wrapper.find<HTMLSelectElement>("#setup-call-ssid").element.value).toBe("9");
    expect(nextButton().attributes("disabled")).toBeUndefined();
    await next(); // Enter in the field submits the form
    expect(wrapper.find(".setup-step-name").text()).toBe("Position");
  });
});

describe("SetupGuide: the SSID of the call", () => {
  it("is a dropdown beside the call, with the (i) of the row; the call field takes the call without a dash", async () => {
    const { wrapper, type, guide } = make();
    const select = () => wrapper.find<HTMLSelectElement>("#setup-call-ssid");
    expect(select().element.closest(".field-control")).toBe(
      wrapper.find("#setup-call").element.closest(".field-control"),
    );
    expect(select().findAll("option")).toHaveLength(16);
    expect(select().element.value).toBe("");
    expect(wrapper.find("#setup-call").element.closest(".field")?.querySelectorAll(".infotip")).toHaveLength(1);
    await type("setup-call", "oh2 abc!");
    expect(wrapper.find<HTMLInputElement>("#setup-call").element.value).toBe("OH2ABC");
    await select().setValue("10");
    expect(guide.fields.call).toBe("OH2ABC-10");
    expect(guide.changes["station/call"]).toBe("OH2ABC-10");
  });

  it("shows the call of the daemon apart, and sends it as it was", () => {
    const config = configValues({ "station/call": "OH2ABC-9" });
    const { wrapper, guide } = make({ config });
    expect(wrapper.find<HTMLInputElement>("#setup-call").element.value).toBe("OH2ABC");
    expect(wrapper.find<HTMLSelectElement>("#setup-call-ssid").element.value).toBe("9");
    expect(guide.changes["station/call"]).toBeUndefined();
  });
});

describe("SetupGuide: the position", () => {
  it("has latitude, longitude and the locator, and the 6 characters of a locator fill the others with the square's centre", async () => {
    const { wrapper, stand, type } = make();
    await stand(1);
    expect(wrapper.findAll(".field label").map((l) => l.text())).toEqual(["Latitude", "Longitude", "Locator"]);
    await type("setup-locator", "KP20ie");
    expect(wrapper.find<HTMLInputElement>("#setup-lat").element.value).toBe("60.1875");
    expect(wrapper.find<HTMLInputElement>("#setup-lon").element.value).toBe("24.7083");
    await type("setup-lat", "60.17");
    await type("setup-lon", "24.94");
    expect(wrapper.find<HTMLInputElement>("#setup-locator").element.value).toBe("KP20le");
    await type("setup-lat", "95");
    expect(wrapper.find(".field-error").text()).toBe("Between -90 and 90");
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeDefined();
  });

  it("asks no browser for its place: the map or the fields give it", async () => {
    const { wrapper, stand, button } = make();
    await stand(1);
    expect(button("Use this computer's location")).toBeUndefined();
    expect(wrapper.find("button.location-pick").text()).toBe("Choose on map");
  });

  it("folds to its head for 'Choose on map' and comes back with Done, or with the click that sets the place", async () => {
    const { wrapper, guide, stand, button } = make();
    await stand(1);
    await button("Choose on map")?.trigger("click");
    expect(wrapper.find(".setup").classes()).toContain("peeking");
    expect(button("Done")).toBeDefined();
    await button("Done")?.trigger("click");
    expect(wrapper.find(".setup").classes()).not.toContain("peeking");
    await button("Choose on map")?.trigger("click");
    guide.place(60.2, 24.9);
    await nextTick();
    expect(wrapper.find(".setup").classes()).not.toContain("peeking");
  });
});

describe("SetupGuide: the position, with the Location control of the My station tab", () => {
  async function onPosition(extra: Record<string, string> = {}) {
    const made = make({ config: fresh(extra) });
    await made.type("setup-call", "oh2abc");
    await made.next();
    return made;
  }
  const place = (wrapper: ReturnType<typeof make>["wrapper"]) => wrapper.find(".location-shown");

  it("has the row Location first: a plain Choose on map and the place as plain text ('Not set' while there is none; nothing to click), and Next waiting for a place", async () => {
    const { wrapper } = await onPosition();
    const first = wrapper.find(".setup-body").element.firstElementChild;
    expect(first?.classList.contains("location-field")).toBe(true);
    expect(wrapper.find(".location-field .field-label").text()).toBe("Location");
    const pick = wrapper.find("button.location-pick");
    expect(pick.text()).toBe("Choose on map");
    expect(pick.classes()).not.toContain("primary");
    expect(wrapper.findAll(".setup .primary").map((b) => b.text())).toEqual(["Next"]); // (the one main action)
    expect([place(wrapper).text(), place(wrapper).classes()]).toEqual(["Not set", expect.arrayContaining(["muted"])]);
    expect(place(wrapper).element.tagName).toBe("SPAN");
    expect(wrapper.find(".location-place").exists()).toBe(false);
    expect(place(wrapper).element.previousElementSibling).toBe(pick.element);
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeDefined();
  });

  it("has the entry (latitude, longitude, locator) open, with the cursor in the latitude, and no 'Enter coordinates or locator' heading", async () => {
    const { wrapper } = await onPosition();
    await flushPromises();
    expect(wrapper.find(".location-entry").exists()).toBe(true);
    expect(wrapper.findAll(".location-entry label").map((l) => l.text())).toEqual(["Latitude", "Longitude", "Locator"]);
    expect(document.activeElement).toBe(wrapper.find("#setup-lat").element);
    expect(wrapper.text()).not.toContain("Enter coordinates");
    expect(wrapper.find(".setup-body details").exists()).toBe(false);
  });

  it("says the place in words when it is set, with the entry open the whole time (a click on the place does nothing: it is no button), the locator filled from the place", async () => {
    const { wrapper, type } = await onPosition({ "station/lat": "60.17", "station/lon": "-24.94" });
    expect(wrapper.find(".location-entry").exists()).toBe(true);
    expect(place(wrapper).text()).toMatch(/^60\.17 N, 24\.94 W · [A-R]{2}\d\d[a-x]{2}$/);
    expect(place(wrapper).classes()).not.toContain("muted");
    expect(wrapper.find<HTMLInputElement>("#setup-locator").element.value).toBe(place(wrapper).text().slice(-6));
    await type("setup-lat", "61");
    expect(place(wrapper).text()).toMatch(/^61 N, 24\.94 W · /);
    await place(wrapper).trigger("click");
    expect(wrapper.find(".location-entry").exists()).toBe(true);
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeUndefined();
  });

  it("says what is wrong with a field under it", async () => {
    const { wrapper, type } = await onPosition({ "station/lat": "60.17", "station/lon": "24.94" });
    await type("setup-lat", "95");
    expect(wrapper.find(".location-entry").exists()).toBe(true);
    expect(wrapper.find(".field-error").text()).toBe("Between -90 and 90");
  });

  it("takes a locator in the same entry: the centre of its square fills the others, which the guide's fields hold and save", async () => {
    const { wrapper, guide, type } = await onPosition();
    await type("setup-locator", "KP20ie");
    expect(guide.fields).toMatchObject({ lat: "60.1875", lon: "24.7083" });
    expect(place(wrapper).text()).toBe("60.1875 N, 24.7083 E · KP20ie");
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeUndefined();
    await type("setup-locator", "SS00aa");
    expect(wrapper.find(".location-entry .field-error").text()).toBe("Not a locator");
    expect(guide.fields).toMatchObject({ lat: "60.1875", lon: "24.7083" });
  });

  it("is set by a click on the map, which shows in the text", async () => {
    const { wrapper, guide } = await onPosition();
    await wrapper.find("button.location-pick").trigger("click");
    guide.place(60.42945, 24.14524);
    await nextTick();
    expect(place(wrapper).text()).toMatch(/^60\.42945 N, 24\.14524 E \u00b7 KP\d\d[a-z]{2}$/);
  });
});

describe("SetupGuide: the symbol", () => {
  it("draws the 12 symbols from the sprite and the house is the one in force", async () => {
    const { wrapper, stand } = make();
    await stand(2);
    const buttons = wrapper.findAll(".setup-symbol");
    expect(buttons.map((b) => b.text())).toEqual(SYMBOL_CHOICES.map((s) => s.name));
    expect(buttons.every((b) => b.find(".symicon .stn-layer").exists())).toBe(true);
    expect(buttons[0]?.find(".stn-layer").attributes("style")).toContain("symbols/primary.png");
    expect(buttons[0]?.attributes("aria-pressed")).toBe("true");
    expect(wrapper.find("#setup-symbol-change").text()).toBe("More symbols…");
    expect(wrapper.find("#setup-symbol-change").classes()).toContain("btn");
    // the symbol in force is nothing to click: the button beside it opens the picker
    expect(wrapper.find(".symbolshown").element.tagName).toBe("SPAN");
    expect(wrapper.find(".symbolbtn").exists()).toBe(false);
    expect(wrapper.find(".symbolfield-name").text()).toBe("House");
  });

  it("sets the table and code from a symbol of the 12, and any other from the picker that the symbol shown under them opens (no More... button)", async () => {
    const { wrapper, guide, stand } = make();
    await stand(2);
    await wrapper.findAll(".setup-symbol")[1]?.trigger("click");
    expect(guide.fields.symbol).toBe("/>");
    expect(wrapper.find(".symbolfield-name").text()).toBe("Car");
    expect(wrapper.findAll(".setup-symbol")[1]?.attributes("aria-pressed")).toBe("true");
    expect(wrapper.findAll(".setup-symbol")[0]?.attributes("aria-pressed")).toBe("false");
    expect(wrapper.find(".sympick").exists()).toBe(false);
    expect(wrapper.findAll("button").some((b) => b.text() === "More...")).toBe(false);
    await wrapper.find("#setup-symbol-change").trigger("click");
    expect(wrapper.find(".sympick").exists()).toBe(true);
    await wrapper.find<HTMLInputElement>(".sympick input[type=search]").setValue("lighthouse");
    await wrapper.find(".sympick-symbol").trigger("click");
    expect(guide.fields.symbol).toBe("\\L");
    expect(wrapper.find(".symbolfield-name").text()).toBe("Lighthouse");
    expect(wrapper.findAll(".setup-symbol").every((b) => b.attributes("aria-pressed") === "false")).toBe(true);
    expect(wrapper.find(".sympick").exists()).toBe(false);
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeUndefined();
  });
});

// The Radio step is live, as the Radio group of the Settings tab is: the same boxes, each change
// saved as it is made, and Finish waiting for one enabled radio with no field in error. Left out:
// RX only, Tune, the level and the scope.
describe("SetupGuide: the radio, on a station of one radio", () => {
  it("is the Radio group's one box as the Settings tab has it: its Enable ticked and greyed, its status line, behind the arrow the type, the port, the speed, Find my radio and the Terminal; then Add radio", async () => {
    const { wrapper, stand } = make({ radios: oneRadio(), ports: ports() });
    await stand(3);
    expect(legends(wrapper)).toEqual(["FM radio"]);
    const enable = wrapper.find<HTMLInputElement>("#setup-radio-1-enabled");
    expect(enable.element.checked).toBe(true);
    expect(enable.element.disabled).toBe(true);
    expect(enable.element.closest(".field")?.getAttribute("title")).toBe(ONLY);
    expect(boxOf(wrapper, "FM radio").find(".radiostatus .tncstatus").exists()).toBe(true);
    expect(wrapper.find<HTMLSelectElement>("#setup-radio-1-type").element.value).toBe("kenwood-tnc2");
    expect(wrapper.findAll("#setup-radio-1-type option").map((o) => o.attributes("value"))).toEqual(
      typeChoices("fm").map((c) => c.value),
    );
    expect(wrapper.findAll("#setup-radio-1-port option").map((o) => o.text())).toEqual([
      "find automatically",
      "/dev/ttyUSB0 - FT232R USB UART",
      "/dev/ttyACM0",
      "/dev/brainbox_3",
      "Other...",
    ]);
    expect(wrapper.find("#setup-radio-1-baud").attributes("placeholder")).toBe("9600");
    expect(wrapper.find("#setup-radio-1-find").text()).toBe("Find my radio");
    expect(wrapper.findAll("summary").map((s) => s.text())).toContain("Terminal");
    expect(labels(wrapper)).toEqual(["Enable", "Radio type", "Port", "Speed", "Add radio"]);
    // named only where the station has several radios
    expect(wrapper.find("#setup-radio-1-name").exists()).toBe(false);
    expect(wrapper.find("#setup-radio-add").exists()).toBe(true);
    expect(wrapper.find("#setup-radio-add-button").text()).toBe("Add");
  });

  it("has ids of its own, none of the Settings tab's: every tab stays mounted, so both are on the page", async () => {
    const { wrapper, stand } = make({ radios: oneRadio() });
    await stand(3);
    const ids = wrapper.findAll(".setup-body [id]").map((e) => e.attributes("id") ?? "");
    expect(ids.length).toBeGreaterThan(5);
    expect(ids.filter((id) => !id.startsWith("setup-") && !id.startsWith("settings-box-setup-"))).toEqual([]);
  });

  it("saves a change at once, as the Settings tab does, and Finish sends only the call, the place and the beacon", async () => {
    const { wrapper, portList, configs, answer, stand, enter, next } = make({ radios: oneRadio() });
    await stand(3);
    portList.value = ports();
    await nextTick();
    await wrapper.find("#setup-radio-1-port").setValue("/dev/ttyUSB0");
    expect(configs().at(-1)).toEqual({ cmd: "set_config", values: { "radio/1/port": "/dev/ttyUSB0" } });
    await answer();
    await enter("setup-radio-1-baud", "4800");
    expect(configs().at(-1)).toEqual({ cmd: "set_config", values: { "radio/1/baud": "4800" } });
    await answer();
    await next();
    expect(configs()).toEqual([
      PLACE,
      { cmd: "set_config", values: { "radio/1/port": "/dev/ttyUSB0" } },
      { cmd: "set_config", values: { "radio/1/baud": "4800" } },
      FINISH,
    ]);
  });

  it("checks the speed as the Settings tab does, and Finish waits while it is wrong", async () => {
    const { wrapper, finish, stand, enter, configs } = make({ radios: oneRadio() });
    await stand(3);
    await enter("setup-radio-1-baud", "12");
    expect(wrapper.find(".setup-body .field-error").text()).toBe("300 to 921600");
    expect(finish().element.disabled).toBe(true);
    expect(configs()).toEqual([PLACE]);
    await enter("setup-radio-1-baud", "57600");
    expect(wrapper.find(".setup-body .field-error").exists()).toBe(false);
    expect(finish().element.disabled).toBe(false);
  });

  it("has no automatic port where the daemon does not search the ports, and Finish waits for a port picked", async () => {
    const { wrapper, finish, portList, stand } = make({ radios: oneRadio() });
    await stand(3);
    portList.value = ports({ search: false });
    await nextTick();
    expect(wrapper.findAll("#setup-radio-1-port option")[0]?.text()).toBe("not set");
    expect(finish().element.disabled).toBe(true);
    await wrapper.find("#setup-radio-1-port").setValue("/dev/ttyUSB0");
    expect(finish().element.disabled).toBe(false);
  });

  it("asks the daemon for the radio's new type, and has the host and the port in place of the serial fields once the radio is KISS over TCP, saved as they are left; Finish waits for a TCP port that is right", async () => {
    const { wrapper, finish, configs, sent, stand, enter, daemon } = make({ radios: oneRadio() });
    await stand(3);
    await wrapper.find("#setup-radio-1-type").setValue("kiss-tcp");
    expect(sent.at(-1)).toEqual({ cmd: "radio_change", radio: 1, type: "kiss-tcp" });
    await tell(daemon, { radios: radiosTopic(radioRow(1, "kiss-tcp")) });
    await flushPromises();
    expect(wrapper.find("#setup-radio-1-port").exists()).toBe(false);
    expect(wrapper.find("#setup-radio-1-baud").exists()).toBe(false);
    expect(wrapper.find<HTMLInputElement>("#setup-radio-1-tcp_host").element.value).toBe("127.0.0.1");
    expect(wrapper.find<HTMLInputElement>("#setup-radio-1-tcp_port").element.value).toBe("8001");
    await enter("setup-radio-1-tcp_port", "70000");
    expect(wrapper.find(".setup-body .field-error").text()).toBe("1 to 65535");
    expect(finish().element.disabled).toBe(true);
    await enter("setup-radio-1-tcp_port", "8002");
    expect(finish().element.disabled).toBe(false);
    expect(configs().at(-1)).toEqual({ cmd: "set_config", values: { "radio/1/tcp_port": "8002" } });
  });

  it("leaves the host for the port of the same TNC without saving it, by the guide's own ids, and saves the two when the pair is left", async () => {
    const { wrapper, configs, stand } = make({ radios: radiosTopic(radioRow(1, "kiss-tcp")) });
    await stand(3);
    const before = configs().length;
    await wrapper.find("#setup-radio-1-tcp_host").setValue("192.168.1.5");
    await wrapper
      .find("#setup-radio-1-tcp_host")
      .trigger("blur", { relatedTarget: wrapper.find("#setup-radio-1-tcp_port").element });
    expect(configs()).toHaveLength(before);
    await wrapper.find("#setup-radio-1-tcp_port").trigger("blur", { relatedTarget: null });
    // of the pair, what changed
    expect(configs().at(-1)).toEqual({ cmd: "set_config", values: { "radio/1/tcp_host": "192.168.1.5" } });
  });

  it("has no port, no speed and no host for the Dummy radio, and Finish does not wait for a port", async () => {
    const { wrapper, finish, portList, stand, daemon } = make({ radios: oneRadio() });
    await stand(3);
    portList.value = ports({ search: false });
    await nextTick();
    expect(finish().element.disabled).toBe(true);
    await tell(daemon, { radios: radiosTopic(radioRow(1, "dummy")) });
    await flushPromises();
    for (const id of ["setup-radio-1-port", "setup-radio-1-baud", "setup-radio-1-tcp_host", "setup-radio-1-tcp_port"])
      expect(wrapper.find(`#${id}`).exists(), id).toBe(false);
    expect(wrapper.find("#setup-radio-1-find").exists()).toBe(false); // (a radio with no serial line)
    expect(finish().element.disabled).toBe(false);
    // the terminal shows the made-up traffic
    expect(wrapper.findAll("summary").map((s) => s.text())).toContain("Terminal");
  });

  it("asks the daemon for the ports when it comes on the screen and again with Refresh", async () => {
    const { sent, stand, button, portList } = make({ radios: oneRadio() });
    await stand(3);
    expect(sent.filter((c) => c.cmd === "list_ports").length).toBeGreaterThanOrEqual(1);
    const asked = sent.filter((c) => c.cmd === "list_ports").length;
    portList.value = ports();
    await nextTick();
    await button("Refresh")?.trigger("click");
    expect(sent.filter((c) => c.cmd === "list_ports")).toHaveLength(asked + 1);
  });
});

describe("SetupGuide: the radio, Find my radio", () => {
  const found = (extra: Partial<RadioSearchMessage> = {}): RadioSearchMessage =>
    radioSearch({
      state: "found",
      port: "COM5",
      baud: 57600,
      profile: "kiss",
      radio: 1,
      number: 0,
      total: 0,
      ...extra,
    });

  it("asks the daemon to find the radio, and what it finds is saved at once as the Settings tab saves it: the type, the port and the speed", async () => {
    const { wrapper, sent, radioSearch, configs, stand } = make({ radios: oneRadio() });
    await stand(3);
    await wrapper.find("#setup-radio-1-find").trigger("click");
    expect(sent.filter((c) => c.cmd === "find_radio")).toEqual([{ cmd: "find_radio", radio: 1 }]);
    radioSearch.value = found({ state: "trying", profile: "", radio_type: "", number: 3, total: 21 });
    await nextTick();
    expect(configs()).toEqual([PLACE]);
    radioSearch.value = found();
    await nextTick();
    expect(sent.filter((c) => c.cmd === "radio_change")).toEqual([{ cmd: "radio_change", radio: 1, type: "kiss" }]);
    expect(configs().at(-1)).toEqual({
      cmd: "set_config",
      values: { "radio/1/port": "COM5", "radio/1/baud": "57600" },
    });
  });

  it("is in the box of a radio with a serial line only: not for KISS over TCP nor the Dummy radio, and back for a serial TNC", async () => {
    const { wrapper, stand, daemon } = make({ radios: oneRadio(), ports: ports() });
    await stand(3);
    expect(wrapper.find("#setup-radio-1-find").exists()).toBe(true);
    for (const [type, there] of [
      ["kiss-tcp", false],
      ["dummy", false],
      ["kiss", true],
    ] as const) {
      await tell(daemon, { radios: radiosTopic(radioRow(1, type)) });
      await flushPromises();
      expect(wrapper.find("#setup-radio-1-find").exists(), type).toBe(there);
    }
  });

  it("is not there where the daemon cannot look for the radio among the ports", async () => {
    const { wrapper, portList, stand } = make({ radios: oneRadio() });
    await stand(3);
    portList.value = ports({ find: false });
    await nextTick();
    expect(wrapper.find("#setup-radio-1-find").exists()).toBe(false);
    expect(wrapper.find("#setup-radio-1-port").exists()).toBe(true);
  });
});

describe("SetupGuide: the radio, on a station of an FM and a Mercury radio", () => {
  /** Radio 1 a serial TNC, on; radio 2 the Mercury modem, off unless `hf` says. */
  const two = (hf: Partial<RadioRow> = { enabled: false, state: "stopped" }, fm: Partial<RadioRow> = {}) =>
    radiosTopic(radioRow(1, "kenwood-tnc2", fm), radioRow(2, "mercury", hf));

  it("has a box each with Name and Remove, the FM radio's Enable greyed while it is the only one on, and no RX only", async () => {
    const { wrapper, stand } = make({ radios: two() });
    await stand(3);
    expect(legends(wrapper)).toEqual(["FM radio", "Mercury radio"]);
    expect(labels(wrapper).filter((l) => l === "RX only")).toEqual([]);
    expect(wrapper.find<HTMLInputElement>("#setup-radio-1-enabled").element.disabled).toBe(true);
    expect(wrapper.find<HTMLInputElement>("#setup-radio-2-enabled").element.checked).toBe(false);
    expect(wrapper.find<HTMLInputElement>("#setup-radio-1-name").attributes("placeholder")).toBe("FM");
    expect(wrapper.find<HTMLButtonElement>("#setup-radio-1-remove").element.disabled).toBe(true);
    expect(wrapper.find<HTMLButtonElement>("#setup-radio-2-remove").element.disabled).toBe(false);
    expect(
      boxOf(wrapper, "Mercury radio")
        .findAll("select, input")
        .map((e) => e.attributes("id")),
    ).toEqual(["setup-radio-2-enabled", "setup-radio-2-name"]);
  });

  it("asks the daemon to switch the Mercury radio on at once, and once it is on shows its type, its sound card, its keying with Test and its frequencies, and no Tune, no level and no scope", async () => {
    const { wrapper, sent, stand, daemon } = make({ radios: two(), ports: ports({ sound_cards: [], keying: "vox" }) });
    await stand(3);
    const above = () => {
      const rows = [...wrapper.find(".setup-body").element.querySelectorAll(".field, legend")];
      return rows
        .slice(
          0,
          rows.findIndex((e) => e.querySelector("#setup-radio-2-enabled") !== null),
        )
        .map((e) => e.textContent);
    };
    const before = above();
    await wrapper.find("#setup-radio-2-enabled").setValue(true);
    expect(sent.filter((c) => c.cmd === "radio_change")).toEqual([{ cmd: "radio_change", radio: 2, enabled: true }]);
    await tell(daemon, { radios: two({}) });
    await flushPromises();
    expect(above()).toEqual(before); // (nothing above the Enable moves when it is ticked)
    expect(wrapper.find<HTMLInputElement>("#setup-radio-1-enabled").element.disabled).toBe(false);
    const hf = boxOf(wrapper, "Mercury radio");
    for (const id of [
      "setup-radio-2-type",
      "setup-radio-2-sound_card",
      "setup-radio-2-keying",
      "setup-radio-2-keying-test",
    ])
      expect(hf.find(`#${id}`).exists(), id).toBe(true);
    expect(hf.find("#setup-hf-frequencies-2").text()).toBe("Show");
    expect(hf.find("#setup-radio-2-tune").exists()).toBe(false);
    expect(hf.find("#setup-radio-2-txlevel").exists()).toBe(false);
    expect(hf.find(".hf-scope").exists()).toBe(false);
  });

  it("is right with the Mercury radio alone, which needs no serial port where the daemon does not search the ports", async () => {
    const { wrapper, finish, stand } = make({
      radios: two({}, { enabled: false, state: "stopped" }),
      ports: ports({ search: false }),
    });
    await stand(3);
    expect(wrapper.find<HTMLInputElement>("#setup-radio-1-enabled").element.checked).toBe(false);
    expect(wrapper.find<HTMLInputElement>("#setup-radio-2-enabled").element.disabled).toBe(true);
    expect(wrapper.find("#setup-radio-1-port").exists()).toBe(false);
    expect(finish().element.disabled).toBe(false);
  });

  it("lets Finish go while one radio on is right, though the other has a field that is wrong", async () => {
    const { finish, stand, enter } = make({ radios: two({}) });
    await stand(3);
    await enter("setup-radio-1-baud", "12");
    expect(finish().element.disabled).toBe(false); // (the HF radio is right: one enabled radio with no field in error)
  });
});

/**
 * The six radios of a station: FM and HF (1, 2), a KISS TNC called Mobile (3), a Dummy HF radio
 * called 20 m (4), a KISS TNC over TCP (5) and a Mercury modem with an eight-wide-letter name (6).
 */
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
const SIX = fresh({}, { "radio/2/sound_card": "plughw:1,0" });
const SIX_LEGENDS = ["FM radio", "Mercury radio", "Mobile", "20 m", "FM radio 3", "WWWWWWWW"];
const css = (file: string) => readFileSync(join(STYLES, file), "utf8");

describe("SetupGuide: the radio, on a station of six radios, on a phone (375 px)", () => {
  const phone = () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    document.documentElement.classList.add("size-phone");
  };

  it("has a box for each radio in the daemon's order, each with its Name, its legend whole, and Add radio last", async () => {
    phone();
    const { wrapper, stand } = make({ config: SIX, radios: sixRadios() });
    await stand(3);
    expect(legends(wrapper)).toEqual(SIX_LEGENDS);
    for (const id of [1, 2, 3, 4, 5, 6])
      expect(wrapper.find(`#setup-radio-${id}-name`).exists(), String(id)).toBe(true);
    expect(wrapper.find<HTMLInputElement>("#setup-radio-6-name").element.value).toBe("WWWWWWWW");
    expect(labels(wrapper).at(-1)).toBe("Add radio");
    expect(wrapper.findAll("[id*='tune'], [id*='txlevel']").map((e) => e.attributes("id"))).toEqual([]);
    expect(wrapper.find(".hf-scope").exists()).toBe(false);
  });

  it("has the rules that keep six boxes within the phone's width: a box never wider than the panel, the panel the width of the screen, its body scrolling, the Name's button wrapping", () => {
    expect(css("setup.css")).toMatch(/\.setup fieldset\.subbox\s*\{[^}]*min-width:\s*0/);
    expect(css("setup.css")).toMatch(/\.setup-body\s*\{[^}]*overflow:\s*auto/);
    expect(css("setup.css")).toMatch(/\.setup \.subbox legend\s*\{[^}]*overflow-wrap:\s*anywhere/);
    expect(css("responsive.css")).toMatch(/\.size-phone \.setup\s*\{[^}]*left:\s*0;[^}]*width:\s*auto/);
    expect(css("settings.css")).toMatch(
      /\.radioname \.field-control,\s*\.radioadd \.field-control\s*\{[^}]*flex-wrap:\s*wrap/,
    );
  });

  it("shows a radio that is off as its Enable and its Name, one that is not connected with its fold open, and none that is removed", async () => {
    const { wrapper, stand } = make({
      config: SIX,
      radios: sixRadios({
        3: { enabled: false, state: "stopped" },
        5: { state: "waiting", problem: { code: "radio.not_connected", params: { name: "FM 3" } } },
        4: { removed: true, enabled: false, state: "stopped" },
      }),
    });
    await stand(3);
    expect(legends(wrapper)).toEqual(["FM radio", "Mercury radio", "Mobile", "FM radio 3", "WWWWWWWW"]);
    expect(
      boxOf(wrapper, "Mobile")
        .findAll("select, input")
        .map((e) => e.attributes("id")),
    ).toEqual(["setup-radio-3-enabled", "setup-radio-3-name"]);
    expect(boxOf(wrapper, "FM radio 3").find(".tncstatus").text()).toBe("Not connected");
    expect(boxOf(wrapper, "FM radio 3").find<HTMLDetailsElement>("details.radiostatus").element.open).toBe(true);
  });

  it("sends a radio's own change by its id, as the Settings tab does", async () => {
    const { wrapper, sent, stand } = make({
      config: SIX,
      radios: sixRadios({ 3: { enabled: false, state: "stopped" } }),
    });
    await stand(3);
    await wrapper.find("#setup-radio-3-enabled").setValue(true);
    expect(sent.at(-1)).toEqual({ cmd: "radio_change", radio: 3, enabled: true });
  });
});

describe("SetupGuide: the radio, on a station with no radio (a fresh installation once the daemon gives none)", () => {
  /** The topic as the daemon tells it once the radio is added. */
  const added = (extra: Partial<RadioRow> = {}) =>
    radiosTopic(radioRow(1, "mercury", { state: "connecting", ...extra }));

  it("is one box, the radio being added: the type from the whole list and Add, which waits for a type; Finish waits for a radio", async () => {
    const { wrapper, finish, sent, stand } = make({ radios: radiosTopic() });
    await stand(3);
    expect(legends(wrapper)).toEqual(["New radio"]);
    // Settings' list, in its groups
    expect(wrapper.findAll("#setup-radio-add option").map((o) => o.attributes("value"))).toEqual([
      "",
      ...addTypeChoices().map((choice) => choice.value),
    ]);
    expect(wrapper.findAll("#setup-radio-add optgroup").map((g) => g.attributes("label"))).toEqual([
      "FM",
      "Mercury",
      "LoRa",
      "Without a radio",
    ]);
    expect(
      addTypeChoices()
        .map((choice) => choice.value)
        .sort(),
    ).toEqual(RADIO_TYPES.map((type) => type.key).sort()); // (every type, once)
    expect(wrapper.find<HTMLButtonElement>("#setup-radio-add-button").element.disabled).toBe(true);
    expect(labels(wrapper)).toEqual(["Add radio"]);
    expect(finish().element.disabled).toBe(true);
    await wrapper.find("#setup-radio-add").setValue("mercury");
    expect(sent.filter((c) => c.cmd === "radio_add")).toEqual([]); // (a type looked at is not added)
  });

  it("adds the radio with Add, and once its row has come its box takes the place of the one being added, with its type's fields and its status at once, its type in focus, and Add radio under it", async () => {
    const { wrapper, finish, sent, stand, daemon } = make({
      radios: radiosTopic(),
      ports: ports({ sound_cards: [], keying: "vox" }),
    });
    await stand(3);
    await wrapper.find("#setup-radio-add").setValue("mercury");
    await wrapper.find("#setup-radio-add-button").trigger("click");
    expect(sent.filter((c) => c.cmd === "radio_add")).toEqual([{ cmd: "radio_add", type: "mercury" }]);
    await tell(daemon, { radioAdded: { type: "radio_added", id: 1 } });
    expect(legends(wrapper)).toEqual(["New radio"]); // (the answer comes before the row)
    await tell(daemon, { radios: added() });
    await flushPromises();
    expect(legends(wrapper)).toEqual(["Mercury radio"]);
    const box = boxOf(wrapper, "Mercury radio");
    expect(box.find<HTMLInputElement>("#setup-radio-1-enabled").element.disabled).toBe(true);
    expect(box.find(".radiostatus .tncstatus").exists()).toBe(true);
    expect(box.find<HTMLDetailsElement>("details.radiostatus").element.open).toBe(true);
    expect(box.find<HTMLSelectElement>("#setup-radio-1-type").element.value).toBe("mercury");
    expect(box.findAll("#setup-radio-1-type option").map((o) => o.attributes("value"))).toEqual(
      typeChoices("hf").map((c) => c.value),
    );
    expect(box.find("#setup-radio-1-sound_card").exists()).toBe(true);
    expect(box.find("#setup-radio-1-keying").exists()).toBe(true);
    expect(document.activeElement?.id).toBe("setup-radio-1-type"); // (its Enable is greyed: the only radio)
    expect(labels(wrapper).at(-1)).toBe("Add radio");
    expect(wrapper.findAll("#setup-radio-add")).toHaveLength(1);
    expect(finish().element.disabled).toBe(false);
  });

  it("stays the box being added when the daemon refuses the add", async () => {
    const { wrapper, lastError, stand, daemon } = make({ radios: radiosTopic() });
    await stand(3);
    await wrapper.find("#setup-radio-add").setValue("kiss");
    await wrapper.find("#setup-radio-add-button").trigger("click");
    lastError.value = toastOf("radio_add: the radio could not be stored; nothing changed", "setting.not_stored");
    await flushPromises();
    expect(legends(wrapper)).toEqual(["New radio"]);
    // added from elsewhere: the guide does not lead to it
    await tell(daemon, { radioAdded: { type: "radio_added", id: 4 }, radios: radiosTopic(radioRow(4, "kiss")) });
    await flushPromises();
    expect(document.activeElement?.id).not.toBe("setup-radio-4-enabled");
  });

  it("waits for the radio it adds, not for a change of the row of one it added before and is removed since", async () => {
    const gone = (name: string) => radioRow(4, "kiss", { removed: true, enabled: false, state: "stopped", name });
    const { wrapper, stand, daemon } = make({ radios: radiosTopic(gone("Old")) });
    await stand(3);
    await tell(daemon, { radioAdded: { type: "radio_added", id: 4 } }); // (added before, and removed since)
    expect(legends(wrapper)).toEqual(["New radio"]);
    await wrapper.find("#setup-radio-add").setValue("kiss");
    await wrapper.find("#setup-radio-add-button").trigger("click");
    await tell(daemon, { radios: radiosTopic(gone("Older")) });
    await flushPromises();
    await tell(daemon, {
      radioAdded: { type: "radio_added", id: 5 },
      radios: radiosTopic(gone("Older"), radioRow(5, "kiss", { number: 2 })),
    });
    await flushPromises();
    expect(document.activeElement?.id).toBe("setup-radio-5-type");
  });
});

describe("SetupGuide: the radio beside the Settings tab, both on the page", () => {
  function both(opts: Made = {}) {
    const made = make(opts);
    const settings = mount(SettingsForm, {
      props: { scope: "settings" },
      global: withDaemon(made.daemon),
      attachTo: document.body,
    });
    return { ...made, settings };
  }

  it("has no id twice on the page", async () => {
    const { stand } = both({ config: SIX, radios: sixRadios() });
    await stand(3);
    const ids = [...document.querySelectorAll("[id]")].map((e) => e.id);
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([]);
    expect(ids).toContain("set-radio-1-enabled");
    expect(ids).toContain("setup-radio-1-enabled");
  });

  it("leads to the box of the radio added in the guide only, and the Settings tab to the box of the radio it added only", async () => {
    const { wrapper, settings, stand, daemon } = both({ config: SIX, radios: sixRadios() });
    await stand(3);
    const add = async (place: VueWrapper, id: string, radio: number) => {
      await place.find(`#${id}`).setValue("kiss");
      await place.find(`#${id}-button`).trigger("click");
      await tell(daemon, { radioAdded: { type: "radio_added", id: radio } });
      const topic = sixRadios();
      for (const made of [7, 8].filter((n) => n <= radio))
        topic.set(String(made), radioRow(made, "kiss", { number: made - 3 }));
      await tell(daemon, { radios: topic });
      await flushPromises();
    };
    await add(wrapper, "setup-radio-add", 7);
    expect(document.activeElement?.id).toBe("setup-radio-7-enabled");
    await add(settings, "set-radio-add", 8);
    expect(document.activeElement?.id).toBe("set-radio-8-enabled");
  });
});

describe("SetupGuide: Finish", () => {
  it("is on the Radio step, the last: Finish, the one primary, in place of Next, and nothing of the map but its quiet line", async () => {
    const { wrapper, stand } = make({
      map: mapState({ state: "downloading", step: "area", percent: 42, downloaded: 1_000_000, radius_km: 150 }),
    });
    await stand(3);
    expect(wrapper.find(".setup-step-name").text()).toBe("Radio");
    expect(wrapper.find("#setup-radius").exists()).toBe(false);
    expect(wrapper.find(".mapfetch-button").exists()).toBe(false);
    expect(wrapper.find(".mapfetch-progress").exists()).toBe(false);
    expect(wrapper.find(".setup-mapline").text()).toBe("Downloading the map of your area…");
    expect(wrapper.findAll(".setup .primary").map((b) => b.text())).toEqual(["Finish"]);
    expect(wrapper.find("button[type=submit]").text()).toBe("Finish");
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeUndefined();
  });

  it("sends the one set_config with the changed keys on Finish and shows 'Saving...' until the daemon answers", async () => {
    const { wrapper, guide, config, sent, stand, next, answer } = make();
    await stand(3);
    await next();
    expect(sent.filter((c) => c.cmd !== "list_ports")).toEqual([PLACE, FINISH]);
    expect(wrapper.find("button[type=submit]").text()).toBe("Saving...");
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeDefined();
    const now = config.value;
    config.value = now && { ...now, values: { ...now.values, "station/call": "OH2XYZ" } };
    await flushPromises();
    expect(guide.open, "another page's change of the settings is no answer").toBe(true);
    await answer();
    expect(guide.open).toBe(false);
    expect(wrapper.find(".setup").exists()).toBe(false);
  });

  it("shows the daemon's refusal under the field it names, on the step that has it", async () => {
    const { wrapper, lastError, stand, next } = make();
    await stand(3);
    await next();
    lastError.value = toastOf("set_config: station/call: call 'OH2ABC-99' has an SSID above 15", "call.ssid", {
      value: "OH2ABC-99",
      max: 15,
    });
    await flushPromises();
    expect(wrapper.find(".setup-step-name").text()).toBe("Call");
    expect(wrapper.find(".field-error").text()).toBe("call 'OH2ABC-99' has an SSID above 15");
    expect(wrapper.find(".setup").exists()).toBe(true);
  });

  /**
   * A port picked on the Radio step and Finish pressed at once: the port's save is sent, then
   * Finish's, and the daemon answers the port's first.
   */
  const portThenFinish = async () => {
    const made = make({ radios: oneRadio(), ports: ports() });
    await made.stand(3);
    await made.wrapper.find("#setup-radio-1-port").setValue("/dev/ttyUSB0");
    await made.next();
    expect(made.configs().slice(-2)).toEqual([
      { cmd: "set_config", values: { "radio/1/port": "/dev/ttyUSB0" } },
      FINISH,
    ]);
    const now = made.config.value;
    made.config.value = now && { ...now, radio_values: { ...now.radio_values, "radio/1/port": "/dev/ttyUSB0" } };
    await flushPromises();
    const port = made.out.shift();
    if (port !== undefined) made.saved.value = { type: "saved", id: port };
    await flushPromises();
    expect(made.guide.open).toBe(true);
    expect(made.finish().text()).toBe("Saving...");
    return made;
  };

  it("waits for its own answer: the answer to a radio's save sent just before is not it, and closes on its own", async () => {
    const { guide, answer } = await portThenFinish();
    await answer();
    expect(guide.open).toBe(false);
  });

  it("shows the daemon's refusal of its save under the field it names when a radio's save was answered first", async () => {
    const { wrapper, guide, lastError } = await portThenFinish();
    lastError.value = toastOf(
      "set_config: station/call: OH2ABC is a placeholder, not a call: set your call first",
      "call.placeholder",
      { call: "OH2ABC" },
    );
    await flushPromises();
    expect(guide.open).toBe(true);
    expect(wrapper.find(".setup-step-name").text()).toBe("Call");
    expect(wrapper.find(".field-error").text()).toBe("OH2ABC is a placeholder, not a call: set your call first");
    // what was typed is still there
    expect(wrapper.find<HTMLInputElement>("#setup-call").element.value).toBe("OH2ABC");
  });

  it("has the radio step, the last, with nothing of the radios before the daemon has told its settings, and Finish waits for them", async () => {
    const { wrapper, guide, config, finish } = make();
    config.value = null;
    guide.step = 3;
    await nextTick();
    expect(wrapper.find(".setup-body").element.children).toHaveLength(0);
    expect(finish().text()).toBe("Finish");
    expect(finish().element.disabled).toBe(true);
  });
});

describe("SetupGuide: the radio, before the daemon has told its radios", () => {
  it("has nothing on the Radio step and Finish waits, then the station's one box once the topic has come: no two boxes of the settings of before in the meantime", async () => {
    const { wrapper, finish, sent, stand, daemon } = make({ radios: null });
    await stand(3);
    expect(wrapper.find(".setup-body").element.children).toHaveLength(0);
    expect(finish().text()).toBe("Finish");
    expect(finish().element.disabled).toBe(true);
    await finish().trigger("click");
    expect(sent.filter((c) => c.cmd === "set_config")).toEqual([PLACE]);
    await tell(daemon, { radios: oneRadio() });
    await flushPromises();
    expect(legends(wrapper)).toEqual(["FM radio"]);
    expect(wrapper.find("#setup-radio-1-name").exists()).toBe(false);
    expect(finish().element.disabled).toBe(false);
  });
});

describe("SetupGuide: the map is made without a click", () => {
  it("says so in one quiet line on the steps while the daemon downloads the map of the area, the last step too", async () => {
    const { wrapper, daemon, guide, stand } = make();
    await stand(2);
    expect(wrapper.find(".setup-mapline").exists()).toBe(false);
    await tell(daemon, { map: mapState({ state: "downloading", step: "area", percent: 20 }) });
    expect(wrapper.find(".setup-mapline").text()).toBe("Downloading the map of your area…");
    expect(wrapper.find(".setup-mapline").attributes("role")).toBe("status");
    guide.go(3);
    await nextTick();
    expect(wrapper.find(".setup-mapline").text()).toBe("Downloading the map of your area…");
    expect(wrapper.find(".mapfetch-progress").exists()).toBe(false);
  });

  it("says the detailed map will download when the computer is online, when the daemon could not fetch it yet", async () => {
    const { wrapper, daemon, stand } = make();
    await stand(2);
    await tell(daemon, {
      map: mapState({ state: "error", problem: { code: "no_build", params: { days: 10 } }, later: true }),
    });
    expect(wrapper.find(".setup-mapline").text()).toBe("The detailed map will download when you are online.");
  });

  it("is gone when the detailed map is there", async () => {
    const { wrapper, daemon, stand } = make();
    await stand(2);
    await tell(daemon, { map: mapState({ state: "downloading" }) });
    expect(wrapper.find(".setup-mapline").exists()).toBe(true);
    await tell(daemon, { map: mapState({ state: "ready", detail: mapFile() }) });
    expect(wrapper.find(".setup-mapline").exists()).toBe(false);
  });
});
