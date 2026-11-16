// A radio of the Sound card type in the Radio group, from the daemon's description of the type alone (RADIO_TYPES): its sound card and its keying chosen from what the daemon lists, Tune, the transmit level within the
// type's own range, and the receive level of the packets it hears, whose row is there before the first packet so that nothing moves when one comes, dimmed while the radio is keyed; and not offered where the
// installation does not carry its program.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { setLocale, t } from "@/i18n";
import { LOCALES } from "@/i18n/locales";
import { portsAsks } from "@/lib/radios";
import { typeChoices, typeText } from "@/lib/settingsradio";
import { rowStatus } from "@/lib/tncstatus";
import type { ModemState, PortsMessage, RadioRow } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { configValues, portRow, radioRow, radiosTopic, soundCard, soundCardModem, status } from "@/test/fixtures";

const ports: PortsMessage = {
  type: "ports",
  sound_cards: [{ id: "plughw:CARD=AIOC,DEV=0", name: "All-In-One-Cable", numbered: "plughw:2,0", default: false, pick: true, held_by: null }],
  keying: "cm108",
  search: true,
  find: true,
  ports: [portRow("/dev/ttyUSB0", "CP2102 USB to UART")],
  radio: 3, // (the answer for the Sound card radio: its own sound cards and keying)
};
const OWN = {
  "radio/3/sound_card": "plughw:CARD=AIOC,DEV=0",
  "radio/3/keying": "cm108",
  "radio/3/tx_gain_db": "0",
  "radio/3/beacon": "true",
  "radio/3/path": "",
  "radio/3/digipeat": "false",
};

function radios(modem: Partial<RadioRow["modem"]> = {}): Map<string, RadioRow> {
  return radiosTopic(
    radioRow(1, "kenwood-tnc2"),
    radioRow(2, "mercury", { enabled: false }),
    radioRow(3, "direwolf", { name: "Attic", number: 2, modem: soundCardModem(modem ?? {}) }),
  );
}

function make(unavailable: string[] = []) {
  const config = configValues({});
  const daemon = fakeDaemon({
    config: { ...config, radio_values: { ...config.radio_values, ...OWN }, radio_defaults: { ...config.radio_defaults, ...OWN } },
    radios: radios(),
    ports,
    status: status({ main_radio: 1, unavailable_types: unavailable }),
  });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon), attachTo: document.body });
  const box = () => {
    const found = wrapper.findAll("fieldset.subbox").find((f) => f.find("legend").text() === "Attic");
    if (!found) throw new Error("no box of the Sound card radio");
    return found;
  };
  return { daemon, wrapper, box };
}

let mounted: ReturnType<typeof make>["wrapper"] | null = null;
afterEach(() => {
  mounted?.unmount();
  mounted = null;
});

describe("a Sound card radio's box", () => {
  it("has the sound card, the keying, Tune, the transmit level within its type's range and the receive level, from the type's description", async () => {
    const { wrapper, box } = make();
    mounted = wrapper;
    await flushPromises();
    const fields = box().text();
    expect(box().find("#set-radio-3-sound_card").exists()).toBe(true);
    expect(box().find("#set-radio-3-keying").exists()).toBe(true);
    expect(box().find("#set-radio-3-tune").exists()).toBe(true);
    expect(box().find("#set-radio-3-txlevel-up").attributes("disabled")).toBeDefined(); // (0 dB is the most Direwolf sends: the type's range is -20 to 0)
    expect(fields).toContain("Receive level");
    expect(box().find(".levelvalue").text()).toBe("–");
    expect(box().find(".scope").exists()).toBe(false); // (no scope: the type cannot)
    expect(fields).not.toContain("Peak"); // (Direwolf says no peak of what it sends: no reading that never comes)
    expect(box().find(".scope-level .infotip").exists()).toBe(true); // (the receive level has its (i), as the HF box's has)
  });

  it("keeps the room of the receive level, so nothing moves when the first packet comes, and dims it while the radio is keyed", async () => {
    const { daemon, wrapper, box } = make();
    mounted = wrapper;
    await flushPromises();
    const rows = () =>
      box()
        .findAll(".field")
        .map((row) => row.find("label").text());
    const before = rows();
    await tell(daemon, { radios: radios({ rx_level: 48 }) });
    await flushPromises();
    expect(rows()).toEqual(before);
    expect(box().find(".levelvalue").text()).toBe("48");
    expect(box().find(".levelfill").classes()).toContain("good");
    expect(box().find(".levelbar").classes()).not.toContain("held");
    await tell(daemon, { radios: radios({ rx_level: 48, keyed: true }) });
    await flushPromises();
    expect(box().find(".levelbar").classes()).toContain("held");
    await tell(daemon, { radios: radios({ rx_level: 140 }) });
    await flushPromises();
    expect(box().find(".levelfill").classes()).toContain("clip");
  });

  it("is not offered by Add radio, nor as a type to change to, where the installation does not carry its program", async () => {
    const offered = make();
    mounted = offered.wrapper;
    await flushPromises();
    expect(
      offered.wrapper
        .find("#set-radio-add")
        .findAll("option")
        .map((o) => o.attributes("value")),
    ).toContain("direwolf");
    offered.wrapper.unmount();
    const mac = make(["direwolf"]);
    mounted = mac.wrapper;
    await flushPromises();
    expect(
      mac.wrapper
        .find("#set-radio-add")
        .findAll("option")
        .map((o) => o.attributes("value")),
    ).not.toContain("direwolf");
    expect(typeChoices("fm").map((c) => c.value)).toContain("direwolf");
    expect(typeChoices("fm", ["direwolf"]).map((c) => c.value)).not.toContain("direwolf"); // (the list a radio's type is changed in, too)
    expect(typeText("direwolf")).toBe("Sound card");
  });

  it("is asked for and takes its own sound cards and proposal, never those of the Mercury radio's answer, as every radio with a sound card does", async () => {
    expect(portsAsks([radioRow(1, "kenwood-tnc2"), radioRow(3, "direwolf")])).toEqual([{ cmd: "list_ports", radio: 3 }]);
    const CODEC = "plughw:CARD=CODEC,DEV=0";
    const empty = { ...OWN, "radio/2/sound_card": CODEC, "radio/2/keying": "rts:/dev/ttyUSB0", "radio/3/sound_card": "", "radio/3/keying": "" }; // (the HF radio has its own already)
    const config = configValues({});
    const hfAnswer: PortsMessage = { ...ports, radio: 2, keying: "rts:/dev/ttyUSB0", sound_cards: [soundCard(CODEC, "USB Audio CODEC", { pick: true })] };
    const daemon = fakeDaemon({
      config: { ...config, radio_values: { ...config.radio_values, ...empty }, radio_defaults: { ...config.radio_defaults, ...OWN } },
      radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"), radioRow(3, "direwolf", { name: "Attic", number: 2, modem: soundCardModem() })),
      ports: hfAnswer,
      portsByRadio: new Map([[2, hfAnswer]]),
      status: status({ main_radio: 1 }),
    });
    const sets = () => daemon.send.mock.calls.filter(([c]) => c.cmd === "set_config").map(([c]) => (c as { values: unknown }).values);
    const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon), attachTo: document.body });
    mounted = wrapper;
    await flushPromises();
    const cards = () => [...wrapper.find<HTMLSelectElement>("#set-radio-3-sound_card").element.options].map((o) => o.value);
    expect(sets()).toEqual([]);
    expect(cards()).not.toContain(CODEC);
    await tell(daemon, {
      portsByRadio: new Map([
        [2, hfAnswer],
        [3, ports],
      ]),
    });
    await flushPromises();
    expect(sets()).toContainEqual({ "radio/3/sound_card": "plughw:CARD=AIOC,DEV=0" });
    expect(cards()).toContain("plughw:CARD=AIOC,DEV=0");
    expect(cards()).not.toContain(CODEC);
  });

  it("says why its modem waits, and has the (i) of its keying, Tune and transmit level, in words of any modem: never Mercury's, the ALC or a steady tone", () => {
    const waiting = (reason: ModemState["reason"]) =>
      rowStatus(radioRow(3, "direwolf", { state: "waiting", modem: soundCardModem({ state: "waiting", reason }) }), Date.now());
    const lines = (["not_installed", "network", "not_started", "sound_card", "keying"] as const).map(waiting);
    expect(lines).toEqual([
      "This installation does not carry this radio's modem",
      "Not run: the modem would be open to the network",
      "The modem could not be started",
      "Sound card could not be opened: choose another",
      "Keying device could not be opened: choose another way of keying",
    ]);
    const tips = [t("settings.keying.tip1"), t("settings.keying.tip2"), t("settings.tune.tip1"), t("settings.txlevel.tip1")];
    for (const words of [...lines, ...tips]) expect(words).not.toMatch(/Mercury|ALC|steady/);
  });

  it("says the same in every language of the page: no Mercury, no ALC, no steady tone in any of them", () => {
    // The steady tone as each language had written it before its words became any modem's.
    const STEADY: Record<string, RegExp> = {
      en: /steady/i,
      de: /Dauerton/i,
      es: /continuo/i,
      fi: /tasainen/i,
      fr: /continue/i,
      it: /continuo/i,
      ja: /連続/,
      nl: /vaste toon/i,
      "pt-BR": /contínuo/i,
    };
    const said = (code: string) => {
      setLocale(code);
      const lines = (["not_installed", "network", "not_started", "sound_card", "keying"] as const).map((reason) =>
        rowStatus(radioRow(3, "direwolf", { state: "waiting", modem: soundCardModem({ state: "waiting", reason }) }), Date.now()),
      );
      return [...lines, t("settings.keying.tip1"), t("settings.keying.tip2"), t("settings.tune.tip1"), t("settings.txlevel.tip1")];
    };
    try {
      const wrong = LOCALES.flatMap(({ code }) =>
        said(code)
          .filter((words) => /Mercury|ALC/.test(words) || (STEADY[code]?.test(words) ?? true))
          .map((words) => `${code}: ${words}`),
      );
      expect(wrong).toEqual([]);
    } finally {
      setLocale("en");
    }
  });
});
