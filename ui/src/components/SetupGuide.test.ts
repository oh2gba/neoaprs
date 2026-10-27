import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref, shallowRef } from "vue";
import SetupGuide from "@/components/SetupGuide.vue";
import type { Toast } from "@/composables/useDaemon";
import { useFindRadio } from "@/composables/useFindRadio";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { SYMBOL_CHOICES } from "@/lib/setup";
import { TNC_PROFILES } from "@/protocol/lists";
import type { Command, ConfigValues, MapState, PortsMessage, RadioSearchMessage } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { configValues, mapFile, mapState, toastOf } from "@/test/fixtures";

const fresh = (extra: Record<string, string> = {}) =>
  configValues({ "beacon/interval_min": "0", "station/call": "", "station/lat": "", "station/lon": "", "serial/baud": "", "serial/port": "", ...extra });
const row = (device: string, description: string) => ({ device, description, hwid: "n/a", vid: null, pid: null });
const ports = (extra: Partial<PortsMessage> = {}): PortsMessage => ({
  type: "ports",
  search: true,
  find: true,
  ports: [row("/dev/ttyUSB0", "FT232R USB UART"), row("/dev/ttyACM0", "n/a")],
  ...extra,
});

function make(opts: { config?: ConfigValues; map?: MapState | null } = {}) {
  const config = ref<ConfigValues | null>(opts.config ?? fresh());
  const lastError = ref<Toast | null>(null);
  const portList = ref<PortsMessage | null>(null);
  const sent: Command[] = [];
  const send = (command: Command) => (sent.push(command), true);
  const guide = useSetupGuide(config, lastError, portList, send);
  guide.show();
  const map = opts.map === undefined ? mapState() : opts.map;
  // Find my radio as the page makes it: while the Radio step is on the screen what it finds goes into the guide's answers
  const radioSearch = shallowRef<RadioSearchMessage | null>(null);
  const settings = { change: () => undefined, expected: () => "" };
  const findRadio = useFindRadio(radioSearch, lastError, shallowRef("open" as const), send, settings, config, () => undefined, guide);
  const daemon = fakeDaemon({ config, lastError, ports: portList, guide, map, send, findRadio });
  const wrapper = mount(SetupGuide, { global: withDaemon(daemon), attachTo: document.body });
  const type = (id: string, text: string) => wrapper.find<HTMLInputElement>(`#${id}`).setValue(text);
  const next = () => wrapper.find("form").trigger("submit");
  const button = (label: string) => wrapper.findAll("button").find((b) => b.text() === label);
  /** Fills the call and the position and stands on the step with this index (1 is the position, 4 the map). */
  const stand = async (step: number) => {
    await type("setup-call", "oh2abc");
    await next();
    await type("setup-lat", "60.17");
    await type("setup-lon", "24.94");
    for (let i = 1; i < step; i++) await next();
  };
  return { wrapper, guide, config, lastError, portList, radioSearch, sent, type, next, button, stand, daemon };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
});

describe("SetupGuide: the frame", () => {
  it("is a panel with a heading per step and no explanation: five steps in the indicator, the step's title, Next", () => {
    const { wrapper } = make();
    expect(wrapper.find("[role='dialog']").attributes("aria-label")).toBe("Setup");
    expect(wrapper.findAll(".setup-dot").map((b) => b.attributes("title"))).toEqual(["Call", "Position", "Symbol", "Radio", "Map"]);
    expect(wrapper.find(".setup-dot.active").text()).toBe("1");
    expect(wrapper.findAll(".setup-dot.done")).toHaveLength(0); // the steps ahead have answers already, but are not done
    expect(wrapper.find(".setup-step-name").text()).toBe("Call");
    expect(wrapper.findAll(".setup-step-name")).toHaveLength(1);
    expect(wrapper.find("button[type=submit]").text()).toBe("Next");
    expect(wrapper.find("p").exists()).toBe(false);
    expect(wrapper.find(".setup-foot button").text()).toBe("Next"); // no Back on the first step
  });

  it("is nothing while closed, and says nothing about the beacon before the last step", async () => {
    const { wrapper, guide, stand } = make();
    const texts: string[] = [];
    await stand(1);
    texts.push(wrapper.text());
    for (let i = 2; i <= 4; i++) {
      guide.go(i - 1);
      await nextTick();
      texts.push(wrapper.text());
    }
    expect(texts.join(" ").toLowerCase()).not.toContain("beacon");
    guide.close();
    await nextTick();
    expect(wrapper.find(".setup").exists()).toBe(false);
  });

  it("tells a new station on the last step that it will beacon every 30 min, with an (i) that says where to change it", async () => {
    const { wrapper, guide, stand } = make();
    await stand(4);
    expect(wrapper.find(".setup-beacon").text()).toContain("Beacon every 30 min");
    expect(wrapper.find(".setup-beacon .info-toggle").exists()).toBe(true);
    expect(guide.changes["beacon/interval_min"]).toBe("30");
  });

  it("says nothing of the beacon, and leaves it as it is, when the guide is run again on a station that has a call", async () => {
    const { wrapper, guide } = make({ config: configValues({ "beacon/interval_min": "0" }) });
    guide.go(4);
    await nextTick();
    expect(wrapper.find(".setup-beacon").exists()).toBe(false);
    expect(guide.changes["beacon/interval_min"]).toBeUndefined();
    const sixty = make({ config: configValues({ "beacon/interval_min": "60" }) });
    sixty.guide.go(4);
    await nextTick();
    expect(sixty.wrapper.find(".setup-beacon").text()).toContain("Beacon every 60 min");
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
    expect(select().element.closest(".field-control")).toBe(wrapper.find("#setup-call").element.closest(".field-control"));
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

describe("SetupGuide: the position, with the Location control of the Beacon tab", () => {
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
    expect(wrapper.find(".symbolshown").element.tagName).toBe("SPAN"); // (the symbol in force is nothing to click: the button beside it opens the picker)
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

describe("SetupGuide: the radio", () => {
  it("asks the daemon for the ports and offers Automatic and the ports with what the system calls them", async () => {
    const { wrapper, sent, portList, stand } = make();
    await stand(3);
    await flushPromises();
    expect(sent).toEqual([{ cmd: "list_ports" }]);
    expect(wrapper.findAll("#setup-profile option").map((o) => o.text())).toEqual(TNC_PROFILES.map((p) => p.name));
    expect(wrapper.find<HTMLSelectElement>("#setup-profile").element.value).toBe("kenwood-tnc2");
    portList.value = ports();
    await nextTick();
    expect(wrapper.findAll("#setup-port option").map((o) => [o.attributes("value"), o.text()])).toEqual([
      ["", "Automatic"],
      ["/dev/ttyUSB0", "/dev/ttyUSB0 - FT232R USB UART"],
      ["/dev/ttyACM0", "/dev/ttyACM0"],
    ]);
    expect(wrapper.find<HTMLInputElement>("#setup-baud").attributes("placeholder")).toBe("9600");
    expect(wrapper.find("#setup-host").exists()).toBe(false);
  });

  it("asks again with Refresh, and the port picked is the answer", async () => {
    const { wrapper, guide, sent, portList, stand, button } = make();
    await stand(3);
    portList.value = ports();
    await button("Refresh")?.trigger("click");
    expect(sent.filter((c) => c.cmd === "list_ports")).toHaveLength(2);
    await wrapper.find("#setup-port").setValue("/dev/ttyUSB0");
    expect(guide.fields.port).toBe("/dev/ttyUSB0");
  });

  it("has no Automatic where the daemon does not search the ports, and Next waits for a pick", async () => {
    const { wrapper, portList, stand } = make();
    await stand(3);
    portList.value = ports({ search: false });
    await nextTick();
    expect(wrapper.findAll("#setup-port option")[0]?.text()).toBe("-");
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeDefined();
    await wrapper.find("#setup-port").setValue("/dev/ttyUSB0");
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeUndefined();
  });

  it("has the host and the port instead of the serial fields for KISS over TCP, and asks for no ports", async () => {
    const { wrapper, sent, stand, type } = make();
    await stand(3);
    await flushPromises();
    await wrapper.find("#setup-profile").setValue("kiss-tcp");
    expect(wrapper.find("#setup-port").exists()).toBe(false);
    expect(wrapper.find("#setup-baud").exists()).toBe(false);
    expect(wrapper.find<HTMLInputElement>("#setup-host").element.value).toBe("127.0.0.1");
    expect(wrapper.find<HTMLInputElement>("#setup-tcpport").element.value).toBe("8001");
    await type("setup-tcpport", "70000");
    expect(wrapper.find(".field-error").text()).toBe("1 to 65535");
    await type("setup-host", "");
    expect(wrapper.find("#setup-host").attributes("placeholder")).toBe("127.0.0.1");
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeDefined();
    expect(sent.filter((c) => c.cmd === "list_ports")).toHaveLength(1); // only the first, for the serial TNC
  });

  it("checks the speed", async () => {
    const { wrapper, stand, type } = make();
    await stand(3);
    await type("setup-baud", "12");
    expect(wrapper.find(".field-error").text()).toBe("300 to 921600");
    await type("setup-baud", "57600");
    expect(wrapper.find(".field-error").exists()).toBe(false);
  });
});

describe("SetupGuide: the radio, Find my radio and the Terminal", () => {
  const found = (extra: Partial<RadioSearchMessage> = {}): RadioSearchMessage => ({
    type: "radio_search",
    state: "found",
    port: "COM5",
    baud: 57600,
    profile: "kiss",
    number: 0,
    total: 0,
    ...extra,
  });

  it("has Find my radio and the Terminal under the fields, the same two as the Settings tab has", async () => {
    const { wrapper, stand } = make();
    await stand(3);
    const button = wrapper.find<HTMLButtonElement>("#setup-find-radio");
    expect(button.text()).toBe("Find my radio");
    expect(button.element.closest(".radiofind")).not.toBeNull();
    expect(wrapper.find(".setup-body").element.innerHTML.indexOf("setup-baud")).toBeLessThan(
      wrapper.find(".setup-body").element.innerHTML.indexOf("setup-find-radio"),
    );
    expect(wrapper.findAll("summary").map((s) => s.text())).toEqual(["Terminal"]);
    expect(wrapper.find("pre.tnclines").exists()).toBe(true);
  });

  it("asks the daemon to find the radio, and what it finds fills the radio type, the port and the speed, to be saved with the rest", async () => {
    const { wrapper, guide, sent, radioSearch, stand } = make();
    await stand(3);
    await wrapper.find("#setup-find-radio").trigger("click");
    expect(sent.filter((c) => c.cmd === "find_radio")).toHaveLength(1);
    radioSearch.value = found({ state: "trying", profile: "", number: 3, total: 21 });
    await nextTick();
    expect(guide.fields.port).toBe("");
    radioSearch.value = found();
    await nextTick();
    expect(guide.fields).toMatchObject({ profile: "kiss", port: "COM5", baud: "57600" });
    expect(wrapper.find<HTMLSelectElement>("#setup-profile").element.value).toBe("kiss");
    expect(wrapper.find<HTMLInputElement>("#setup-baud").element.value).toBe("57600");
    expect(guide.changes).toMatchObject({ "tnc/profile": "kiss", "serial/port": "COM5", "serial/baud": "57600" });
    expect(sent.some((c) => c.cmd === "set_config")).toBe(false); // (it is saved at Finish, not by the search)
  });

  it("leaves the speed of the profile alone for a port that has none", async () => {
    const { guide, radioSearch, stand, wrapper } = make();
    await stand(3);
    await wrapper.find("#setup-find-radio").trigger("click");
    radioSearch.value = found({ port: "bt://AA:BB:CC:DD:EE:FF", baud: null });
    await nextTick();
    expect(guide.fields).toMatchObject({ port: "bt://AA:BB:CC:DD:EE:FF", baud: "" });
  });

  it("is not there where the daemon cannot look for the radio among the ports", async () => {
    const { wrapper, portList, stand } = make();
    await stand(3);
    portList.value = ports({ find: false });
    await nextTick();
    expect(wrapper.find("#setup-find-radio").exists()).toBe(false);
    expect(wrapper.find("#setup-port").exists()).toBe(true);
  });

  it("opens the terminal on the radio the answers name: the radio's settings are put in force when it is opened, and nothing when they already are", async () => {
    const { wrapper, sent, portList, stand } = make();
    await stand(3);
    portList.value = ports();
    await nextTick();
    await wrapper.find("#setup-port").setValue("/dev/ttyUSB0");
    const details = wrapper.find<HTMLDetailsElement>("details");
    details.element.open = true;
    await details.trigger("toggle");
    expect(sent.filter((c) => c.cmd === "set_config")).toEqual([{ cmd: "set_config", values: { "serial/port": "/dev/ttyUSB0" } }]); // (not the call, not the position)
    details.element.open = false;
    await details.trigger("toggle");
    expect(sent.filter((c) => c.cmd === "set_config")).toHaveLength(1);
    const quiet = make({ config: configValues() });
    quiet.guide.go(3);
    await nextTick();
    const other = quiet.wrapper.find<HTMLDetailsElement>("details");
    other.element.open = true;
    await other.trigger("toggle");
    expect(quiet.sent.some((c) => c.cmd === "set_config")).toBe(false);
  });

  it("has no port, no speed and no host for the Dummy radio, and Next does not wait for a port", async () => {
    const { wrapper, guide, sent, portList, stand } = make();
    await stand(3);
    portList.value = ports({ search: false });
    await nextTick();
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeDefined();
    await wrapper.find("#setup-profile").setValue("dummy");
    for (const id of ["setup-port", "setup-baud", "setup-host", "setup-tcpport", "setup-find-radio"]) expect(wrapper.find(`#${id}`).exists(), id).toBe(false);
    expect(wrapper.findAll("button").some((b) => b.text() === "Refresh")).toBe(false);
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeUndefined();
    expect(wrapper.findAll("summary").map((s) => s.text())).toEqual(["Terminal"]); // (the terminal shows the made-up traffic)
    expect(wrapper.find<HTMLSelectElement>("#setup-profile").text()).toContain("Dummy (no radio, made-up traffic)");
    expect(guide.changes).toMatchObject({ "tnc/profile": "dummy" });
    expect(Object.keys(guide.changes).filter((k) => k.startsWith("serial/") || k.startsWith("tcp/"))).toEqual([]);
    const details = wrapper.find<HTMLDetailsElement>("details");
    details.element.open = true;
    await details.trigger("toggle");
    expect(sent.filter((c) => c.cmd === "set_config")).toEqual([{ cmd: "set_config", values: { "tnc/profile": "dummy" } }]);
  });

  it("is on the screen only while the Radio step is, for what Find my radio fills", async () => {
    const { guide, radioSearch, config, sent } = make();
    guide.go(0);
    expect(guide.onRadio).toBe(false);
    config.value = configValues();
    radioSearch.value = found();
    await nextTick();
    expect(guide.fields.port).toBe(configValues().values["serial/port"] ?? "");
    expect(sent).toEqual([]);
  });
});

describe("SetupGuide: the map and Finish", () => {
  it("has the radius with the one plain Download map button on its own row under it, and Finish, the one primary, in place of Next", async () => {
    const { wrapper, stand } = make();
    await stand(4);
    expect(wrapper.find(".setup-step-name").text()).toBe("Map");
    expect(wrapper.findAll(".field label").map((l) => l.text())).toEqual(["Radius", "Detailed map"]);
    expect(wrapper.find<HTMLInputElement>("#setup-radius").attributes("placeholder")).toBe("150");
    expect(wrapper.find("#setup-maxzoom").exists()).toBe(false);
    expect(wrapper.findAll(".mapfetch-button").map((b) => b.text())).toEqual(["Download map"]);
    expect(wrapper.find(".mapfetch-button").classes()).not.toContain("primary");
    expect(wrapper.find(".mapfetch-button").element.closest(".field")?.classList.contains("action-row")).toBe(true);
    expect(wrapper.find(".mapfetch-button").element.parentElement?.firstElementChild).toBe(wrapper.find(".mapfetch-button").element);
    expect(wrapper.findAll(".setup .primary").map((b) => b.text())).toEqual(["Finish"]);
    expect(wrapper.find("button[type=submit]").text()).toBe("Finish");
  });

  it("has Download map on while the daemon has no position yet (the guide saves it first), and off for a wrong radius", async () => {
    const { wrapper, stand, type } = make({ map: mapState({ blocked: "no position", box: null }) });
    await stand(4);
    const mapButtons = () => wrapper.findAll(".mapfetch-button");
    expect(mapButtons().every((b) => b.attributes("disabled") === undefined)).toBe(true);
    await type("setup-radius", "5");
    expect(mapButtons().every((b) => b.attributes("disabled") !== undefined)).toBe(true);
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeDefined();
  });

  it("saves first and then estimates, with one set_config in all, and Finish after it sends nothing more", async () => {
    const { wrapper, guide, config, sent, stand, next } = make({ map: mapState({ blocked: "no position", box: null }) });
    await stand(4);
    await wrapper.findAll(".mapfetch-button")[0]?.trigger("click");
    expect(sent.filter((c) => c.cmd === "set_config")).toHaveLength(1);
    expect(sent.some((c) => c.cmd === "map_estimate")).toBe(false);
    expect(wrapper.findAll(".mapfetch-button").every((b) => b.attributes("disabled") !== undefined)).toBe(true);
    const now = config.value;
    config.value = now && { ...now, values: { ...now.values, "station/call": "OH2ABC", "station/lat": "60.17", "station/lon": "24.94" } };
    await flushPromises();
    expect(sent.at(-1)).toEqual({ cmd: "map_estimate" });
    await next();
    expect(sent.filter((c) => c.cmd === "set_config")).toHaveLength(1);
    expect(guide.open).toBe(false);
  });

  it("sends the one set_config with the changed keys on Finish and shows 'Saving...' until the daemon answers", async () => {
    const { wrapper, guide, config, sent, stand, next } = make();
    await stand(4);
    await next();
    expect(sent.filter((c) => c.cmd !== "list_ports")).toEqual([
      { cmd: "set_config", values: { "station/call": "OH2ABC", "station/lat": "60.17", "station/lon": "24.94", "beacon/interval_min": "30" } },
    ]);
    expect(wrapper.find("button[type=submit]").text()).toBe("Saving...");
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeDefined();
    const now = config.value;
    config.value = now && { ...now, values: { ...now.values, "station/call": "OH2ABC", "station/lat": "60.17", "station/lon": "24.94" } };
    await flushPromises();
    expect(guide.open).toBe(false);
    expect(wrapper.find(".setup").exists()).toBe(false);
  });

  it("shows the daemon's refusal under the field it names, on the step that has it", async () => {
    const { wrapper, lastError, stand, next } = make();
    await stand(4);
    await next();
    lastError.value = toastOf("set_config: station/call: 'OH2ABC-99' is not a call");
    await flushPromises();
    expect(wrapper.find(".setup-step-name").text()).toBe("Call");
    expect(wrapper.find(".field-error").text()).toBe("'OH2ABC-99' is not a call");
    expect(wrapper.find(".setup").exists()).toBe(true);
  });

  it("has the radio and the map steps, with no default of the daemon to show, before it has told its settings", async () => {
    const { wrapper, guide, config } = make();
    config.value = null;
    guide.step = 3;
    await nextTick();
    expect(wrapper.find<HTMLSelectElement>("#setup-profile").exists()).toBe(true);
    expect(wrapper.find("#setup-baud").attributes("placeholder")).toBe("9600"); // (the speed of the profile)
    guide.step = 4;
    await nextTick();
    expect(wrapper.find("#setup-radius").attributes("placeholder")).toBe("(default)");
  });

  it("has no map panel while the daemon has not told its map", async () => {
    const { wrapper, stand } = make({ map: null });
    await stand(4);
    expect(wrapper.find(".mapfetch-button").exists()).toBe(false);
    expect(wrapper.find(".mapfetch-notes").exists()).toBe(false);
    expect(wrapper.find("button[type=submit]").text()).toBe("Finish");
  });
});

describe("SetupGuide: the map is made without a click", () => {
  it("says so in one quiet line on the steps while the daemon downloads the map of the area, and says nothing on the Map step, which shows the bar", async () => {
    const { wrapper, daemon, guide, stand } = make();
    await stand(2);
    expect(wrapper.find(".setup-mapline").exists()).toBe(false);
    await tell(daemon, { map: mapState({ state: "downloading", step: "area", percent: 20 }) });
    expect(wrapper.find(".setup-mapline").text()).toBe("Downloading the map of your area…");
    expect(wrapper.find(".setup-mapline").attributes("role")).toBe("status");
    guide.go(4);
    await nextTick();
    expect(wrapper.find(".setup-mapline").exists()).toBe(false);
    expect(wrapper.find(".mapfetch-progress").exists()).toBe(true);
  });

  it("says the detailed map will download when the computer is online, when the daemon could not fetch it yet", async () => {
    const { wrapper, daemon, stand } = make();
    await stand(2);
    await tell(daemon, { map: mapState({ state: "error", problem: "no daily build was found (is there a connection?)", later: true }) });
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
