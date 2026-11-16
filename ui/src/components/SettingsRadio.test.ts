import { flushPromises as flush, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { shallowRef } from "vue";
import FindRadioToast from "@/components/FindRadioToast.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { useFindRadio } from "@/composables/useFindRadio";
import type { ModemState, PortsMessage, RadioRow, RadioSearchMessage } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, fmRow, hfRow, portRow, radioRow, radioSearch, radiosTopic, soundCard } from "@/test/fixtures";

// The Radio group of the Settings tab for a station of an FM radio (radio 1, a serial TNC) and an HF radio (radio 2, the Mercury modem): each worked by its own row of the topic `radios` and its own settings
// (`radio/<id>/<key>`), its Enable and type by `radio_change`. The station of many radios is ManyRadiosPage.test.ts's.
const ports = (find = true): PortsMessage => ({
  type: "ports",
  sound_cards: [],
  keying: "",
  search: find,
  find,
  ports: [portRow("/dev/ttyUSB0", "FT232R USB UART")],
  radio: null,
});

const FM_OFF = fmRow({ enabled: false, state: "stopped" });
const HF_OFF = hfRow({ enabled: false, state: "stopped" });
/** Radio 1 on, radio 2 off: the default. */
const ONE = [fmRow(), HF_OFF];
const BOTH = [fmRow(), hfRow()];
const HF_ONLY = [FM_OFF, hfRow()];
/** Radio 2's own settings. */
const hfValues = (extra: Record<string, string> = {}) => ({
  "radio/2/beacon": "true",
  "radio/2/sound_card": "plughw:1,0",
  "radio/2/keying": "vox",
  "radio/2/tx_gain_db": "0",
  ...extra,
});

function make(more: Given = {}, rows: RadioRow[] = ONE, values: Record<string, string> = hfValues(), station: Record<string, string> = {}) {
  const daemon = fakeDaemon({ config: configValues(station, values), radios: radiosTopic(...rows), ports: ports(), ...more });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
  const group = wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Radio");
  if (!group) throw new Error("no Radio group");
  return { wrapper, group, daemon, send: daemon.send };
}

/** One of the two boxes of the Radio group, by its legend. */
const boxOf = (group: ReturnType<typeof make>["group"], legend: string) => {
  const found = group.findAll("fieldset.subbox").find((f) => f.find("legend").text() === legend);
  if (!found) throw new Error(`no ${legend} box`);
  return found;
};
const fm = (group: ReturnType<typeof make>["group"]) => boxOf(group, "FM radio");
const hf = (group: ReturnType<typeof make>["group"]) => boxOf(group, "Mercury radio");
const fold = (group: ReturnType<typeof make>["group"]) => fm(group).find<HTMLDetailsElement>("details.radiostatus");
const hfFold = (group: ReturnType<typeof make>["group"]) => hf(group).find<HTMLDetailsElement>("details.radiostatus");
/** The ids of the controls of a box that are not inside its fold. */
const outside = (box: ReturnType<typeof boxOf>, folded: HTMLDetailsElement) =>
  box
    .findAll("select, input, .tnclines")
    .filter((e) => !folded.contains(e.element))
    .map((e) => e.attributes("id"));

const ONLY = "The station's only radio that is on";

describe("the Radio group of the Settings tab", () => {
  it("has the RX only tickbox first, then the FM radio and the Mercury radio in a box each, each beginning with its Enable tickbox", () => {
    const { group } = make({}, BOTH);
    expect(group.find(".field").find("label").text()).toBe("RX only");
    expect(group.findAll("fieldset.subbox legend").map((l) => l.text())).toEqual(["FM radio", "Mercury radio"]);
    for (const [box, id] of [
      [fm(group), "set-radio-1-enabled"],
      [hf(group), "set-radio-2-enabled"],
    ] as const) {
      const first = box.find(".field");
      expect(first.find("label").text()).toBe("Enable");
      expect(first.find("input").attributes("type")).toBe("checkbox");
      expect(first.find("input").attributes("id")).toBe(id);
      // (with both radios on, each box has its Name and Remove between its Enable and its status: plan section 6, "In each: Enable; Name and Remove, outside the status fold")
      const name = first.element.nextElementSibling;
      expect(name?.querySelector("label")?.textContent).toBe("Name");
      expect(name?.nextElementSibling).toBe(box.find("details.radiostatus").element);
    }
    expect(group.find<HTMLInputElement>("#set-radio-1-enabled").element.checked).toBe(true);
    expect(group.find<HTMLInputElement>("#set-radio-2-enabled").element.checked).toBe(true);
    expect(group.find(".group-body").element.firstElementChild).toBe(group.find(".field").element); // (the RX only tickbox is the first row)
  });

  it("has an (i) on each Enable, with the picture of the two radios", async () => {
    const { group } = make({}, BOTH);
    for (const box of [fm(group), hf(group)]) {
      expect(box.find(".field .info-toggle").exists()).toBe(true);
      await box.find(".field .info-toggle").trigger("click");
      expect(box.find(".info-text svg").attributes("data-picture")).toBe("tworadios");
    }
  });

  it("is, while the Mercury radio is not ticked, the FM radio as it was and the Mercury box as its Enable row and its Name alone, and the Enable of the only radio is greyed with a title that says why", () => {
    const { group } = make();
    expect(hf(group).find("details").exists()).toBe(false);
    // (plan section 6: "Name and Remove, outside the status fold, so that a radio that is off can be renamed and removed": the HF radio that is off has them, and its Remove works; the FM radio's, the only one on, is off)
    expect(
      hf(group)
        .findAll("select, input")
        .map((e) => e.attributes("id")),
    ).toEqual(["set-radio-2-enabled", "set-radio-2-name"]);
    expect(hf(group).find<HTMLButtonElement>("#set-radio-2-remove").element.disabled).toBe(false);
    expect(fm(group).find<HTMLButtonElement>("#set-radio-1-remove").element.disabled).toBe(true);
    expect(hf(group).find<HTMLInputElement>("#set-radio-2-enabled").element.disabled).toBe(false);
    expect(fold(group).element.open).toBe(false);
    expect(fm(group).find<HTMLInputElement>("#set-radio-1-enabled").element.disabled).toBe(true);
    expect(fm(group).find("#set-radio-1-enabled").element.closest(".field")?.getAttribute("title")).toBe(ONLY);
    expect(fm(group).find("#set-radio-1-enabled").element.closest(".field")?.classList.contains("disabled")).toBe(true);
    expect(fm(group).find("#set-radio-1-enabled").element.closest(".field")?.querySelector(".info-toggle")).not.toBeNull(); // (the (i) still opens)
  });

  it("is, while only the Mercury radio is ticked, the FM box as its Enable row and its Name alone and the Mercury Enable greyed", () => {
    const { group } = make({}, HF_ONLY);
    expect(fm(group).find("details").exists()).toBe(false);
    expect(
      fm(group)
        .findAll("select, input")
        .map((e) => e.attributes("id")),
    ).toEqual(["set-radio-1-enabled", "set-radio-1-name"]); // (plan section 6: the Name of a radio that is off, outside the fold)
    expect(fm(group).find<HTMLInputElement>("#set-radio-1-enabled").element.disabled).toBe(false);
    expect(hf(group).find<HTMLInputElement>("#set-radio-2-enabled").element.disabled).toBe(true);
    expect(hf(group).find("#set-radio-2-enabled").element.closest(".field")?.getAttribute("title")).toBe(ONLY);
    for (const id of ["#set-radio-2-sound_card", "#set-radio-2-keying"]) expect(hf(group).find(id).exists(), id).toBe(true);
  });

  it("greys neither Enable while both radios are ticked", () => {
    const { group } = make({}, BOTH);
    expect(group.findAll<HTMLInputElement>("#set-radio-1-enabled, #set-radio-2-enabled").map((e) => e.element.disabled)).toEqual([false, false]);
    expect(group.findAll(".field.disabled")).toHaveLength(0);
  });

  it("shows the state and the status line of the FM radio, and keeps its fields and the Terminal behind a fold that is closed while the radio is connected", () => {
    const { group } = make();
    expect(fold(group).element.open).toBe(false);
    const head = fold(group).find("summary.statushead");
    expect(head.find(".statetext").text()).toBe("connected");
    expect(head.find(".tncstatus").text()).toBe("Last packet 30 s ago");
    expect(head.find("button").exists()).toBe(false);
    for (const id of ["#set-radio-1-type", "#set-radio-1-port", "#set-radio-1-baud", "#set-radio-1-find"]) expect(fold(group).find(id).exists(), id).toBe(true);
    expect(outside(fm(group), fold(group).element)).toEqual(["set-radio-1-enabled", "set-radio-1-name"]); // (its Name is outside the fold: plan section 6)
  });

  it("is open when the FM radio is not connected, and opens when it stops being connected", async () => {
    expect(fold(make({}, [fmRow({ state: "waiting", problem: { code: "radio.not_connected", params: {} } }), HF_OFF]).group).element.open).toBe(true);
    const { group, daemon } = make();
    expect(fold(group).element.open).toBe(false);
    await tell(daemon, { radios: radiosTopic(fmRow({ state: "silent", problem: null }), HF_OFF) });
    expect(fold(group).element.open).toBe(true);
  });

  it("has the pattern and skip settings nowhere on the page", () => {
    const { wrapper } = make();
    expect(wrapper.find("#set-serial-pattern").exists()).toBe(false);
    expect(wrapper.find("#set-serial-skip").exists()).toBe(false);
  });

  it("has the state of the Mercury radio from its row when it is ticked, open until it is connected, with the modem's own words", async () => {
    const { group, daemon } = make({}, [fmRow(), hfRow({ state: "connecting" }, { state: "starting" })]);
    expect(hfFold(group).find(".statetext").text()).toBe("connecting");
    expect(hfFold(group).element.open).toBe(true);
    expect(fold(group).find(".statetext").text()).toBe("connected");
    const lines = [{ at: "2026-10-21T12:00:00Z", text: "NeoAPRS: opened the modem" }];
    await tell(daemon, { radios: radiosTopic(fmRow(), hfRow({ lines })) });
    expect(hfFold(group).find(".statetext").text()).toBe("connected");
    expect(hfFold(group).find(".tncstatus").text()).toBe("DATAC3 · Listening · Last packet 30 s ago");
    await tell(daemon, { radios: radiosTopic(fmRow(), hfRow({ lines }, { keyed: true })) });
    expect(hfFold(group).find(".tncstatus").text()).toBe("DATAC3 · Transmitting… · Last packet 30 s ago");
    await tell(daemon, { radios: radiosTopic(fmRow(), hfRow({ lines }, { busy: true })) });
    expect(hfFold(group).find(".tncstatus").text()).toBe("DATAC3 · Channel busy, waiting · Last packet 30 s ago");
    expect(hfFold(group).find(".tnclines").text()).toContain("NeoAPRS: opened");
  });

  it("asks the daemon to switch the Mercury radio on at once, and the FM radio off once both are on", async () => {
    const { group, send, daemon } = make();
    await group.find("#set-radio-2-enabled").setValue(true);
    expect(send).toHaveBeenCalledWith({ cmd: "radio_change", radio: 2, enabled: true });
    await tell(daemon, { radios: radiosTopic(...BOTH) });
    await group.find("#set-radio-1-enabled").setValue(false);
    expect(send).toHaveBeenCalledWith({ cmd: "radio_change", radio: 1, enabled: false });
  });

  it("asks for the ports and the sound cards of the Mercury radio when it is on, and not when it is off", async () => {
    const { send, daemon } = make();
    expect(send).not.toHaveBeenCalledWith({ cmd: "list_ports", radio: 2 });
    await tell(daemon, { radios: radiosTopic(...BOTH) });
    expect(send).toHaveBeenCalledWith({ cmd: "list_ports", radio: 2 });
    send.mockClear();
    await tell(daemon, { radios: radiosTopic(...ONE) });
    expect(send).not.toHaveBeenCalled();
  });
});

describe("Find my radio", () => {
  it("is a button of the fold, as big as the buttons beside it, and asks the daemon for the radio of its box", async () => {
    const { group, send } = make();
    const button = group.find<HTMLButtonElement>("#set-radio-1-find");
    expect(button.text()).toBe("Find my radio");
    expect(button.classes()).toEqual(["btn"]);
    expect(fold(group).element.contains(button.element)).toBe(true);
    await button.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "find_radio", radio: 1 });
    expect(button.element.disabled).toBe(true);
  });

  it("is in the box of a radio with a serial line only (plan section 6a): not for KISS over TCP nor the Dummy radio", () => {
    for (const [type, there] of [
      ["kenwood-tnc2", true],
      ["kiss", true],
      ["kiss-tcp", false],
      ["dummy", false],
    ] as const) {
      expect(
        make({}, [radioRow(1, type), HF_OFF])
          .group.find("#set-radio-1-find")
          .exists(),
        type,
      ).toBe(there);
    }
  });

  it("writes nothing beside the button or under the fields", () => {
    const { group } = make();
    const row = group.find(".radiofind");
    expect(row.text()).toBe("Find my radio");
    expect(row.findAll("*")).toHaveLength(1);
  });

  it("is not there where the daemon does not look for the radio among the ports", () => {
    expect(
      make({ ports: ports(false) })
        .group.find("#set-radio-1-find")
        .exists(),
    ).toBe(false);
  });

  it("is waiting while a search runs", async () => {
    const daemon = fakeDaemon({ config: configValues(), radios: radiosTopic(...ONE), ports: ports() });
    const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
    expect(wrapper.find<HTMLButtonElement>("#set-radio-1-find").element.disabled).toBe(false);
    daemon.findRadio.start();
    await wrapper.vm.$nextTick();
    expect(wrapper.find<HTMLButtonElement>("#set-radio-1-find").element.disabled).toBe(true);
  });
});

describe("the toast of Find my radio", () => {
  function running() {
    const message = shallowRef<RadioSearchMessage | null>(null);
    const send = vi.fn(() => true);
    const find = useFindRadio(
      message,
      shallowRef(null),
      shallowRef("open" as const),
      send,
      { change: vi.fn(), expected: () => "" },
      shallowRef(configValues()),
      () => undefined,
    );
    return { find, message, send };
  }

  it("is not there until a search runs, then says the try and has Cancel", async () => {
    const { find, message, send } = running();
    const wrapper = mount(FindRadioToast, { props: { find } });
    expect(wrapper.find(".toast").exists()).toBe(false);
    find.start();
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".toast").text()).toBe("Looking for the radio…Cancel");
    message.value = radioSearch({ number: 2 });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".toast span").text()).toBe("Looking for the radio: /dev/ttyUSB0 at 9600 (2 of 14)");
    await wrapper.find("button").trigger("click");
    expect(send).toHaveBeenLastCalledWith({ cmd: "find_radio_cancel" });
  });

  it("goes when the search ends", async () => {
    const { find, message } = running();
    const wrapper = mount(FindRadioToast, { props: { find } });
    find.start();
    message.value = radioSearch({ state: "cancelled", port: "", baud: null, number: 0, total: 0 });
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".toast").exists()).toBe(false);
  });
});

describe("the Mercury radio's box in the Radio group", () => {
  const cards = (): PortsMessage => ({
    ...ports(),
    radio: 2,
    keying: "rts:/dev/ttyUSB0",
    sound_cards: [
      soundCard("plughw:1,0", "USB AUDIO  CODEC USB Audio", { default: true, pick: true }),
      soundCard("plughw:0,0", "HDA Intel PCH", { default: false, pick: false }),
    ],
  });
  const on = hfValues();
  const empty = hfValues({ "radio/2/sound_card": "", "radio/2/keying": "" });
  const sets = (send: ReturnType<typeof make>["send"]) =>
    send.mock.calls.filter(([c]) => c.cmd === "set_config").map(([c]) => (c as { values: unknown }).values);

  it("has the sound card and the keying as its two fields, and no port, speed, host or TCP port", () => {
    const { group } = make({ ports: cards() }, BOTH, on);
    for (const id of ["#set-radio-2-sound_card", "#set-radio-2-keying"]) expect(hfFold(group).find(id).exists(), id).toBe(true);
    for (const id of ["#set-radio-2-port", "#set-radio-2-baud", "#set-radio-2-tcp_host", "#set-radio-2-tcp_port"])
      expect(hf(group).find(id).exists(), id).toBe(false);
    for (const id of ["#set-radio-1-sound_card", "#set-radio-1-keying"]) expect(fm(group).find(id).exists(), id).toBe(false);
    const keying = group.find<HTMLSelectElement>("#set-radio-2-keying");
    expect([...keying.element.options].map((o) => o.value)).toEqual(["vox", "cm108", "rts:/dev/ttyUSB0", "dtr:/dev/ttyUSB0"]);
    expect(keying.element.value).toBe("vox");
  });

  it("offers the sound cards by the system's name with the id as the hover title, and no find automatically and no Other", () => {
    const { group } = make({ ports: cards() }, BOTH, on);
    const card = group.find<HTMLSelectElement>("#set-radio-2-sound_card");
    expect([...card.element.options].map((o) => o.text)).toEqual(["USB AUDIO  CODEC USB Audio", "HDA Intel PCH"]);
    expect([...card.element.options].map((o) => o.title)).toEqual(["plughw:1,0", "plughw:0,0"]);
    expect([...card.element.options].map((o) => o.value)).not.toContain("");
    expect(card.element.value).toBe("plughw:1,0");
    const keying = group.find<HTMLSelectElement>("#set-radio-2-keying");
    expect([...card.element.options, ...keying.element.options].map((o) => o.text)).not.toContain("find automatically");
    expect(hf(group).findAll(".port-found")).toHaveLength(0);
    expect(
      hf(group)
        .findAll("button")
        .some((b) => b.text() === "Refresh"),
    ).toBe(true);
  });

  it("preselects the daemon's proposal for both while the settings are empty, and stores the card and then the keying as the settings", async () => {
    const { group, send, daemon } = make({ ports: cards() }, BOTH, empty);
    const card = group.find<HTMLSelectElement>("#set-radio-2-sound_card");
    const keying = group.find<HTMLSelectElement>("#set-radio-2-keying");
    expect(card.element.value).toBe("plughw:1,0");
    expect(keying.element.value).toBe("rts:/dev/ttyUSB0");
    expect([...keying.element.options].map((o) => o.value)).not.toContain("");
    expect(sets(send)).toEqual([{ "radio/2/sound_card": "plughw:1,0" }]);
    await tell(daemon, { config: configValues({}, { ...empty, "radio/2/sound_card": "plughw:1,0" }) });
    await flush();
    expect(sets(send)).toEqual([{ "radio/2/sound_card": "plughw:1,0" }, { "radio/2/keying": "rts:/dev/ttyUSB0" }]);
  });

  it("stores nothing where the settings name a card and a keying, or the daemon proposes none", async () => {
    const chosen = make({ ports: cards() }, BOTH, on);
    await flush();
    expect(sets(chosen.send)).toEqual([]);
    const none = make({ ports: ports() }, BOTH, empty);
    await flush();
    expect(sets(none.send)).toEqual([]);
  });

  it("is there whatever the FM radio's type is, and the FM radio's box has no sound card", () => {
    for (const type of ["kenwood-tnc2", "kiss", "kiss-tcp", "dummy"]) {
      const { group } = make({}, [radioRow(1, type), hfRow()], on);
      expect(hf(group).find("#set-radio-2-sound_card").exists(), type).toBe(true);
      expect(hf(group).find("#set-radio-2-keying").exists(), type).toBe(true);
      expect(fm(group).find("[id$='-sound_card']").exists(), type).toBe(false);
    }
  });

  it("sends the chosen card and keying as any choice", async () => {
    const { group, send, daemon } = make({ ports: cards() }, BOTH, on);
    await group.find<HTMLSelectElement>("#set-radio-2-sound_card").setValue("plughw:0,0");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "radio/2/sound_card": "plughw:0,0" } });
    await tell(daemon, { config: configValues({}, { ...on, "radio/2/sound_card": "plughw:0,0" }) }); // (the daemon's answer: the form sends one change at a time)
    await group.find<HTMLSelectElement>("#set-radio-2-keying").setValue("rts:/dev/ttyUSB0");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "radio/2/keying": "rts:/dev/ttyUSB0" } });
  });

  it("has the suggested frequencies the daemon says as a row to read, in the Mercury box of the Mercury modem only", () => {
    const { group } = make({ ports: cards() }, BOTH, on);
    const row = hfFold(group).find("#hf-frequencies-2");
    expect(row.findAll(".freq").map((line) => line.text())).toEqual([
      "80 m 3.5850 MHz USB",
      "40 m 7.0541 MHz USB",
      "20 m 14.1070 MHz USB",
      "6 m 50.6200 MHz USB",
    ]);
    expect(row.element.tagName).toBe("OUTPUT"); // (text to read, not an input box that takes no typing)
    expect(row.element.closest(".field")?.querySelector("label")?.textContent).toBe("Suggested frequencies");
    expect(fm(group).find("[id^='hf-frequencies']").exists()).toBe(false);
    expect(
      make({ ports: cards() }, [fmRow(), radioRow(2, "dummy-hf")], on)
        .group.find("[id^='hf-frequencies']")
        .exists(),
    ).toBe(false);
  });

  it("keeps a stored card that the daemon does not list as one more choice", () => {
    const { group } = make({ ports: cards() }, BOTH, hfValues({ "radio/2/sound_card": "plughw:7,0" }));
    const card = group.find<HTMLSelectElement>("#set-radio-2-sound_card");
    expect(card.element.value).toBe("plughw:7,0");
    expect([...card.element.options].map((o) => o.value)).toEqual(["plughw:1,0", "plughw:0,0", "plughw:7,0"]);
  });
});

describe("the fold of each box follows its own radio", () => {
  it("opens the Mercury fold alone when the Mercury radio is not connected, and the FM fold alone when the FM radio is not", async () => {
    const { group, daemon } = make({}, BOTH);
    expect([fold(group).element.open, hfFold(group).element.open]).toEqual([false, false]);
    await tell(daemon, { radios: radiosTopic(fmRow(), hfRow({ state: "connecting" }, { state: "starting" })) });
    expect([fold(group).element.open, hfFold(group).element.open]).toEqual([false, true]);
    const other = make({}, BOTH);
    await tell(other.daemon, { radios: radiosTopic(fmRow({ state: "silent" }), hfRow()) });
    expect([fold(other.group).element.open, hfFold(other.group).element.open]).toEqual([true, false]);
  });

  it("leaves the FM fold as it was when the Mercury radio's type is changed and the Mercury radio goes through connecting, in both directions", async () => {
    const { group, send, daemon } = make({}, BOTH);
    expect(fold(group).element.open).toBe(false);
    await hfFold(group).find("#set-radio-2-type").setValue("dummy-hf");
    expect(send).toHaveBeenCalledWith({ cmd: "radio_change", radio: 2, type: "dummy-hf" });
    await tell(daemon, { radios: radiosTopic(fmRow(), radioRow(2, "dummy-hf", { state: "connecting" })) });
    expect(hfFold(group).element.open).toBe(true);
    expect(fold(group).element.open).toBe(false);
    await tell(daemon, { radios: radiosTopic(fmRow(), radioRow(2, "dummy-hf")) });
    await hfFold(group).find("#set-radio-2-type").setValue("mercury");
    expect(send).toHaveBeenCalledWith({ cmd: "radio_change", radio: 2, type: "mercury" });
    await tell(daemon, { radios: radiosTopic(fmRow(), hfRow({ state: "connecting" }, { state: "starting" })) });
    expect(fold(group).element.open).toBe(false);
    expect(fold(group).find(".statetext").text()).toBe("connected");
  });
});

describe("the Mercury radio's type, Tune and the keying test", () => {
  const running = (test: ModemState["test"] = "", extra: Partial<RadioRow> = {}, modem: Partial<ModemState> = {}) => [
    fmRow(),
    hfRow(extra, { test, ...modem }),
  ];
  const tune = (group: ReturnType<typeof make>["group"]) => hf(group).find<HTMLButtonElement>("#set-radio-2-tune");
  const keyTest = (group: ReturnType<typeof make>["group"]) => hf(group).find<HTMLButtonElement>("#set-radio-2-keying-test");

  it("has the Radio type as the first field of the Mercury box, the Mercury modem first and the Dummy Mercury radio last, with the dummy picture on its (i)", async () => {
    const { group } = make({}, running());
    const type = hfFold(group).find<HTMLSelectElement>("#set-radio-2-type");
    expect(
      hfFold(group)
        .findAll("select, input")
        .map((e) => e.attributes("id"))[0],
    ).toBe("set-radio-2-type");
    expect([...type.element.options].map((o) => o.value)).toEqual(["mercury", "dummy-hf"]);
    expect(type.element.value).toBe("mercury");
    const field = type.element.closest(".field");
    expect(field?.querySelector("label")?.textContent).toBe("Radio type");
    hfFold(group).find("#set-radio-2-type").element.closest(".field")!.querySelector<HTMLElement>(".info-toggle")!.click();
    await flush();
    expect(field?.querySelector(".info-text svg")?.getAttribute("data-picture")).toBe("dummy");
  });

  it("has Tune in an action row of its own under the fields, as big as Find my radio, and Test beside the Keying field; a press asks the daemon for this radio", async () => {
    const { group, send } = make({}, running());
    expect(tune(group).element.closest(".field.action-row")?.querySelector("label")?.textContent).toBe("Tuning tone");
    expect(tune(group).text()).toBe("TuneStop");
    expect(tune(group).find(".twowords").exists()).toBe(true);
    expect(keyTest(group).element.closest(".field")?.querySelector("#set-radio-2-keying")).not.toBeNull();
    expect(keyTest(group).text()).toBe("Test");
    expect(hf(group).find("p").exists()).toBe(false);
    await tune(group).trigger("click");
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_tune", radio: 2, on: true });
    await keyTest(group).trigger("click");
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_key_test", radio: 2 });
  });

  it("reads Stop while the tone is on, stops it at a second press, and the status line says Tuning… or Keyed; Test waits meanwhile", async () => {
    const { group, send, daemon } = make({}, running("tune"));
    expect(tune(group).find(".twowords-off").text()).toBe("Tune");
    expect(hfFold(group).find(".tncstatus").text()).toBe("DATAC3 · Tuning… · Last packet 30 s ago");
    expect(keyTest(group).element.disabled).toBe(true);
    await tune(group).trigger("click");
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_tune", radio: 2, on: false });
    await tell(daemon, { radios: radiosTopic(...running("key")) });
    expect(hfFold(group).find(".tncstatus").text()).toBe("DATAC3 · Keyed · Last packet 30 s ago");
    expect(tune(group).element.disabled).toBe(true);
    expect(keyTest(group).element.disabled).toBe(true);
  });

  it("has no aria-pressed on Tune: the label that swaps to Stop says it", () => {
    for (const test of ["", "tune"] as const) expect(tune(make({}, running(test)).group).attributes("aria-pressed"), test).toBeUndefined();
  });

  it("has both off while a frame keys the radio or the channel is heard busy, as the daemon would refuse them; Stop of a tone on stays", () => {
    for (const held of [{ keyed: true }, { busy: true }]) {
      const { group } = make({}, running("", {}, held));
      expect(tune(group).element.disabled, JSON.stringify(held)).toBe(true);
      expect(keyTest(group).element.disabled, JSON.stringify(held)).toBe(true);
    }
    const tone = make({}, running("tune", {}, { keyed: true }));
    expect(tune(tone.group).element.disabled).toBe(false);
    expect(tune(tone.group).find(".twowords-off").text()).toBe("Tune");
  });

  it("has both off while RX only is ticked, with the title that says so, and while the modem is not running", () => {
    const rx = make({}, running(), hfValues(), { "station/transmit": "false" });
    expect(tune(rx.group).element.disabled).toBe(true);
    expect(keyTest(rx.group).element.disabled).toBe(true);
    expect(tune(rx.group).attributes("title")).toBe("RX only: nothing is sent");
    expect(keyTest(rx.group).attributes("title")).toBe("RX only: nothing is sent");
    const waiting = make({}, running("", { state: "waiting" }, { state: "waiting", reason: "stopped" }));
    expect(tune(waiting.group).element.disabled).toBe(true);
    expect(keyTest(waiting.group).element.disabled).toBe(true);
    expect(tune(waiting.group).attributes("title")).toBeUndefined();
  });

  it("is, with the Dummy Mercury radio chosen, the type alone: no sound card, no keying, no Tune, and the muted Dummy pill with its line", () => {
    const { group } = make({}, [fmRow(), radioRow(2, "dummy-hf")], { "radio/2/beacon": "true" });
    expect(
      hfFold(group)
        .findAll("select, input")
        .map((e) => e.attributes("id")),
    ).toEqual(["set-radio-2-type"]);
    expect(tune(group).exists()).toBe(false);
    expect(keyTest(group).exists()).toBe(false);
    expect(hfFold(group).find(".statetext").text()).toBe("Dummy");
    expect(hfFold(group).find(".statetext").classes()).toContain("tnc-dummy");
    expect(hfFold(group).find(".tncstatus").text()).toBe("Dummy Mercury radio: made-up distant stations, your frames on the speakers, nothing goes on the air");
  });

  it("has nothing of the Mercury radio's socket in the status line: Connecting… while it connects, the modem's words while it runs", () => {
    const connecting = make({}, running("", { state: "connecting" }));
    expect(hfFold(connecting.group).find(".tncstatus").text()).toBe("Connecting…");
    const heard = make({}, running("", {}, { snr: 3.4 }));
    expect(hfFold(heard.group).find(".tncstatus").text()).toBe("DATAC3 · Listening · SNR 3 dB · Last packet 30 s ago");
    expect(hf(heard.group).text()).not.toContain("127.0.0.1");
  });
});
