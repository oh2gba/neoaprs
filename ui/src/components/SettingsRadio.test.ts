import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { shallowRef } from "vue";
import FindRadioToast from "@/components/FindRadioToast.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { useFindRadio } from "@/composables/useFindRadio";
import type { PortsMessage, RadioSearchMessage } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, hfState, tncState } from "@/test/fixtures";

const ports = (find = true): PortsMessage => ({
  type: "ports",
  sound_cards: [],
  search: find,
  find,
  ports: [{ device: "/dev/ttyUSB0", description: "FT232R USB UART", hwid: "n/a", vid: null, pid: null }],
});

function make(more: Given = {}, extra: Record<string, string> = {}) {
  const daemon = fakeDaemon({ config: configValues(extra), tnc: tncState(), ports: ports(), ...more });
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
const hf = (group: ReturnType<typeof make>["group"]) => boxOf(group, "HF radio");
const fold = (group: ReturnType<typeof make>["group"]) => fm(group).find<HTMLDetailsElement>("details.radiostatus");
const hfFold = (group: ReturnType<typeof make>["group"]) => hf(group).find<HTMLDetailsElement>("details.radiostatus");
/** The ids of the controls of a box that are not inside its fold. */
const outside = (box: ReturnType<typeof boxOf>, folded: HTMLDetailsElement) =>
  box
    .findAll("select, input, .tnclines")
    .filter((e) => !folded.contains(e.element))
    .map((e) => e.attributes("id"));

const BOTH = { "hf/enabled": "true" };
const HF_ONLY = { "fm/enabled": "false", "hf/enabled": "true" };
const ONLY = "The station's only radio: tick the other first";

describe("the Radio group of the Settings tab", () => {
  it("has the RX only tickbox first, then the FM radio and the HF radio in a box each, each beginning with its Enable tickbox", () => {
    const { group } = make({ hf: hfState() }, BOTH);
    expect(group.find(".field").find("label").text()).toBe("RX only");
    expect(group.findAll("fieldset.subbox legend").map((l) => l.text())).toEqual(["FM radio", "HF radio"]);
    for (const [box, id] of [
      [fm(group), "set-fm-enabled"],
      [hf(group), "set-hf-enabled"],
    ] as const) {
      const first = box.find(".field");
      expect(first.find("label").text()).toBe("Enable");
      expect(first.find("input").attributes("type")).toBe("checkbox");
      expect(first.find("input").attributes("id")).toBe(id);
      expect(first.element.nextElementSibling).toBe(box.find("details.radiostatus").element);
    }
    expect(group.find<HTMLInputElement>("#set-fm-enabled").element.checked).toBe(true);
    expect(group.find<HTMLInputElement>("#set-hf-enabled").element.checked).toBe(true);
    expect(group.find("legend").element.nextElementSibling).toBe(group.find(".field").element); // (the RX only tickbox is the first row)
  });

  it("has an (i) on each Enable, with the picture of the two radios", async () => {
    const { group } = make({ hf: hfState() }, BOTH);
    for (const box of [fm(group), hf(group)]) {
      expect(box.find(".field .info-toggle").exists()).toBe(true);
      await box.find(".field .info-toggle").trigger("click");
      expect(box.find(".info-text svg").attributes("data-picture")).toBe("tworadios");
    }
  });

  it("is, while the HF radio is not ticked, the FM radio as it was and the HF box as its Enable row alone, and the Enable of the only radio is greyed with a title that says why", () => {
    const { group } = make();
    expect(hf(group).find("details").exists()).toBe(false);
    expect(
      hf(group)
        .findAll("select, input")
        .map((e) => e.attributes("id")),
    ).toEqual(["set-hf-enabled"]);
    expect(hf(group).find<HTMLInputElement>("#set-hf-enabled").element.disabled).toBe(false);
    expect(fold(group).element.open).toBe(false);
    expect(fm(group).find<HTMLInputElement>("#set-fm-enabled").element.disabled).toBe(true);
    expect(fm(group).find("#set-fm-enabled").element.closest(".field")?.getAttribute("title")).toBe(ONLY);
    expect(fm(group).find("#set-fm-enabled").element.closest(".field")?.classList.contains("disabled")).toBe(true);
    expect(fm(group).find("#set-fm-enabled").element.closest(".field")?.querySelector(".info-toggle")).not.toBeNull(); // (the (i) still opens)
  });

  it("is, while only the HF radio is ticked, the FM box as its Enable row alone and the HF Enable greyed", () => {
    const { group } = make({ hf: hfState() }, HF_ONLY);
    expect(fm(group).find("details").exists()).toBe(false);
    expect(
      fm(group)
        .findAll("select, input")
        .map((e) => e.attributes("id")),
    ).toEqual(["set-fm-enabled"]);
    expect(fm(group).find<HTMLInputElement>("#set-fm-enabled").element.disabled).toBe(false);
    expect(hf(group).find<HTMLInputElement>("#set-hf-enabled").element.disabled).toBe(true);
    expect(hf(group).find("#set-hf-enabled").element.closest(".field")?.getAttribute("title")).toBe(ONLY);
    for (const id of ["#set-mercury-sound_card", "#set-mercury-keying"]) expect(hf(group).find(id).exists(), id).toBe(true);
  });

  it("greys neither Enable while both radios are ticked", () => {
    const { group } = make({ hf: hfState() }, BOTH);
    expect(group.findAll<HTMLInputElement>("#set-fm-enabled, #set-hf-enabled").map((e) => e.element.disabled)).toEqual([false, false]);
    expect(group.findAll(".field.disabled")).toHaveLength(0);
  });

  it("shows the state and the status line of the FM radio, and keeps its fields and the Terminal behind a fold that is closed while the radio is connected", () => {
    const { group } = make();
    expect(fold(group).element.open).toBe(false);
    const head = fold(group).find("summary.statushead");
    expect(head.find(".statetext").text()).toBe("connected");
    expect(head.find(".tncstatus").text()).toBe("Last packet 30 s ago");
    expect(head.find("button").exists()).toBe(false);
    for (const id of ["#set-tnc-profile", "#set-serial-port", "#set-serial-baud", "#find-radio"]) expect(fold(group).find(id).exists(), id).toBe(true);
    expect(outside(fm(group), fold(group).element)).toEqual(["set-fm-enabled"]);
  });

  it("is open when the FM radio is not connected, and opens when it stops being connected", async () => {
    expect(fold(make({ tnc: tncState({ state: "waiting", problem: "no KISS frames", path: "" }) }).group).element.open).toBe(true);
    const { group, daemon } = make();
    expect(fold(group).element.open).toBe(false);
    await tell(daemon, { tnc: tncState({ state: "silent", silent_since: null }) });
    expect(fold(group).element.open).toBe(true);
  });

  it("has the pattern and skip settings nowhere on the page", () => {
    const { wrapper } = make();
    expect(wrapper.find("#set-serial-pattern").exists()).toBe(false);
    expect(wrapper.find("#set-serial-skip").exists()).toBe(false);
  });

  it("has the state of the HF radio from the hf topic when it is ticked, open until it is connected, with the modem's own words", async () => {
    const { group, daemon } = make({ hf: hfState({ state: "connecting", describe: "starting Mercury", problem: "" }) }, BOTH);
    expect(hfFold(group).find(".statetext").text()).toBe("connecting");
    expect(hfFold(group).element.open).toBe(true);
    expect(fold(group).find(".statetext").text()).toBe("connected");
    await tell(daemon, { hf: hfState() });
    expect(hfFold(group).find(".statetext").text()).toBe("connected");
    expect(hfFold(group).find(".tncstatus").text()).toBe("Last packet 30 s ago");
    const modem = hfState().modem;
    if (modem === null) throw new Error("no modem");
    await tell(daemon, { hf: hfState({ modem: { ...modem, keyed: true } }) });
    expect(hfFold(group).find(".tncstatus").text()).toBe("Transmitting…");
    await tell(daemon, { hf: hfState({ modem: { ...modem, busy: true } }) });
    expect(hfFold(group).find(".tncstatus").text()).toBe("Channel busy, waiting");
    expect(hfFold(group).find(".tnclines").text()).toContain("NeoAPRS: opened");
  });

  it("applies a tick of the HF radio at once, and unticking FM once both are on, as any choice", async () => {
    const { group, send, daemon } = make();
    await group.find("#set-hf-enabled").setValue(true);
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "hf/enabled": "true" } });
    await tell(daemon, { config: configValues(BOTH) }); // (the daemon's answer: the form sends one change at a time)
    await group.find("#set-fm-enabled").setValue(false);
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "fm/enabled": "false" } });
  });

  it("asks for the ports and the sound cards again when HF is ticked, and not when it is unticked", async () => {
    const { send, daemon } = make();
    expect(send).not.toHaveBeenCalledWith({ cmd: "list_ports" });
    await tell(daemon, { config: configValues(BOTH) });
    expect(send).toHaveBeenCalledWith({ cmd: "list_ports" });
    send.mockClear();
    await tell(daemon, { config: configValues({ "hf/enabled": "false" }) });
    expect(send).not.toHaveBeenCalled();
  });
});

describe("Find my radio", () => {
  it("is a button of the fold, as big as the buttons beside it, and asks the daemon", async () => {
    const { group, send } = make();
    const button = group.find<HTMLButtonElement>("#find-radio");
    expect(button.text()).toBe("Find my radio");
    expect(button.classes()).toEqual(["btn"]);
    expect(fold(group).element.contains(button.element)).toBe(true);
    await button.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "find_radio" });
    expect(button.element.disabled).toBe(true);
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
        .group.find("#find-radio")
        .exists(),
    ).toBe(false);
  });

  it("is waiting while a search runs", async () => {
    const daemon = fakeDaemon({ config: configValues(), tnc: tncState(), ports: ports() });
    const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon) });
    expect(wrapper.find<HTMLButtonElement>("#find-radio").element.disabled).toBe(false);
    daemon.findRadio.start();
    await wrapper.vm.$nextTick();
    expect(wrapper.find<HTMLButtonElement>("#find-radio").element.disabled).toBe(true);
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
    message.value = { type: "radio_search", state: "trying", port: "/dev/ttyUSB0", baud: 9600, profile: "", number: 2, total: 14 };
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".toast span").text()).toBe("Looking for the radio: /dev/ttyUSB0 at 9600 (2 of 14)");
    await wrapper.find("button").trigger("click");
    expect(send).toHaveBeenLastCalledWith({ cmd: "find_radio_cancel" });
  });

  it("goes when the search ends", async () => {
    const { find, message } = running();
    const wrapper = mount(FindRadioToast, { props: { find } });
    find.start();
    message.value = { type: "radio_search", state: "cancelled", port: "", baud: null, profile: "", number: 0, total: 0 };
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".toast").exists()).toBe(false);
  });
});

describe("the HF radio's box in the Radio group", () => {
  const cards = (): PortsMessage => ({
    ...ports(),
    sound_cards: [
      { id: "plughw:1,0", name: "USB Audio CODEC", default: true },
      { id: "plughw:0,0", name: "HDA Intel PCH", default: false },
    ],
  });
  const on = { "hf/enabled": "true", "mercury/keying": "vox" };

  it("has the sound card and the keying as its two fields, and no port, speed, host or TCP port", () => {
    const { group } = make({ ports: cards(), hf: hfState() }, on);
    for (const id of ["#set-mercury-sound_card", "#set-mercury-keying"]) expect(hfFold(group).find(id).exists(), id).toBe(true);
    for (const id of ["#set-serial-port", "#set-serial-baud", "#set-tcp-host", "#set-tcp-port", "#set-tnc-profile"])
      expect(hf(group).find(id).exists(), id).toBe(false);
    for (const id of ["#set-mercury-sound_card", "#set-mercury-keying"]) expect(fm(group).find(id).exists(), id).toBe(false);
    const card = group.find<HTMLSelectElement>("#set-mercury-sound_card");
    expect([...card.element.options].map((o) => o.text)).toEqual([
      "find automatically",
      "plughw:1,0 - USB Audio CODEC",
      "plughw:0,0 - HDA Intel PCH",
      "Other...",
    ]);
    expect(card.element.value).toBe("");
    const keying = group.find<HTMLSelectElement>("#set-mercury-keying");
    expect([...keying.element.options].map((o) => o.value)).toEqual(["", "vox", "cm108", "rts:/dev/ttyUSB0", "dtr:/dev/ttyUSB0"]);
    expect(keying.element.value).toBe("vox");
  });

  it("offers find automatically first for both, and says beside each what the daemon chose (the hf topic's modem) while the setting is empty", () => {
    const { group } = make({ ports: cards(), hf: hfState() }, { ...on, "mercury/sound_card": "", "mercury/keying": "" });
    const card = group.find<HTMLSelectElement>("#set-mercury-sound_card");
    expect([...card.element.options].map((o) => o.text)[0]).toBe("find automatically");
    expect(card.element.value).toBe("");
    const keying = group.find<HTMLSelectElement>("#set-mercury-keying");
    expect([...keying.element.options].map((o) => o.text)[0]).toBe("find automatically");
    expect(keying.element.value).toBe("");
    expect(
      hf(group)
        .findAll(".port-found")
        .map((e) => e.text()),
    ).toEqual(["found: plughw:1,0", "found: RTS on /dev/ttyUSB0"]);
    const chosen = make({ ports: cards(), hf: hfState() }, { ...on, "mercury/sound_card": "plughw:1,0", "mercury/keying": "vox" });
    expect(hf(chosen.group).findAll(".port-found")).toHaveLength(0);
  });

  it("is there whatever the FM radio's type is, and the FM radio's modem is never looked at", () => {
    for (const profile of ["kenwood-tnc2", "kiss", "kiss-tcp", "dummy"]) {
      const { group } = make({ hf: hfState() }, { ...on, "tnc/profile": profile });
      expect(hf(group).find("#set-mercury-sound_card").exists(), profile).toBe(true);
      expect(hf(group).find("#set-mercury-keying").exists(), profile).toBe(true);
      expect(fm(group).find("#set-mercury-sound_card").exists(), profile).toBe(false);
    }
    const { group } = make({ tnc: tncState({ modem: hfState().modem }), hf: null }, on);
    expect(hf(group).findAll(".port-found")).toHaveLength(0);
  });

  it("sends the chosen card and keying as any choice", async () => {
    const { group, send, daemon } = make({ ports: cards(), hf: hfState() }, on);
    await group.find<HTMLSelectElement>("#set-mercury-sound_card").setValue("plughw:1,0");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "mercury/sound_card": "plughw:1,0" } });
    await tell(daemon, { config: configValues({ ...on, "mercury/sound_card": "plughw:1,0" }) }); // (the daemon's answer: the form sends one change at a time)
    await group.find<HTMLSelectElement>("#set-mercury-keying").setValue("rts:/dev/ttyUSB0");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "mercury/keying": "rts:/dev/ttyUSB0" } });
  });
});
