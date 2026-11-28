// A radio of the Sound card type in the Radio group, from the daemon's description of the type
// alone (RADIO_TYPES): its sound card and keying chosen from what the daemon lists, Tune, the
// transmit level within the type's range, and the receive level, whose row is there before the
// first packet so that nothing moves, dimmed while the radio is keyed. The type is not offered
// where the installation does not carry its program.
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
  sound_cards: [
    {
      id: "plughw:CARD=AIOC,DEV=0",
      name: "All-In-One-Cable",
      numbered: "plughw:2,0",
      default: false,
      capture: true,
      playback: true,
      pick: true,
      held_by: null,
    },
  ],
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
    config: {
      ...config,
      radio_values: { ...config.radio_values, ...OWN },
      radio_defaults: { ...config.radio_defaults, ...OWN },
    },
    radios: radios(),
    ports,
    status: status({ unheard_radio: 1, unavailable_types: unavailable }),
  });
  const wrapper = mount(SettingsForm, {
    props: { scope: "settings" },
    global: withDaemon(daemon),
    attachTo: document.body,
  });
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
    // 0 dB is the most Direwolf sends: the type's range is -20 to 0
    expect(box().find("#set-radio-3-txlevel-up").attributes("disabled")).toBeDefined();
    expect(fields).toContain("Receive level");
    expect(box().find(".levelvalue").text()).toBe("–");
    expect(box().find(".scope").exists()).toBe(false); // (no scope: the type cannot)
    expect(fields).not.toContain("Peak"); // (Direwolf says no peak of what it sends: no reading that never comes)
    // the receive level has its (i), as the HF box's has
    expect(box().find(".scope-level .infotip").exists()).toBe(true);
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

  it("asks for the level ten times a second while its row is in view and follows it, the row's level until it comes, and stops asking when the row goes out of view", async () => {
    const original = globalThis.IntersectionObserver;
    const observers: { target: Element | null; run: (entries: { isIntersecting: boolean }[]) => void }[] = [];
    globalThis.IntersectionObserver = class {
      constructor(run: (entries: { isIntersecting: boolean }[]) => void) {
        observers.push({ target: null, run });
      }
      observe(target: Element): void {
        const made = observers[observers.length - 1];
        if (made) made.target = target;
      }
      disconnect(): void {}
    } as unknown as typeof IntersectionObserver;
    const { daemon, wrapper, box } = make();
    globalThis.IntersectionObserver = original;
    // the Receive level row, not the Transmit level row
    const seen = (entries: { isIntersecting: boolean }[]) =>
      observers.filter((o) => o.target?.querySelector(".levelbar")).forEach((o) => o.run(entries));
    mounted = wrapper;
    await flushPromises();
    const levelAsks = () =>
      daemon.send.mock.calls.map(([command]) => command).filter((command) => command.cmd === "radio_level");
    expect(levelAsks()).toEqual([]);
    seen([{ isIntersecting: true }]);
    expect(levelAsks()).toEqual([{ cmd: "radio_level", radio: 3, on: true }]);
    await tell(daemon, { radios: radios({ rx_level: 30 }) });
    await flushPromises();
    expect(box().find(".levelvalue").text()).toBe("30");
    await tell(daemon, { radioLevels: new Map([[3, 61]]) });
    await flushPromises();
    expect(box().find(".levelvalue").text()).toBe("61");
    await tell(daemon, { radios: radios({ rx_level: 31 }) });
    await flushPromises();
    // the row's level, every two seconds, does not stand over the level now
    expect(box().find(".levelvalue").text()).toBe("61");
    await tell(daemon, { radioLevels: new Map([[3, null]]) });
    await flushPromises();
    expect(box().find(".levelvalue").text()).toBe("31");
    seen([{ isIntersecting: false }]);
    expect(levelAsks()).toEqual([
      { cmd: "radio_level", radio: 3, on: true },
      { cmd: "radio_level", radio: 3, on: false },
    ]);
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
    // the list a radio's type is changed in, too
    expect(typeChoices("fm", ["direwolf"]).map((c) => c.value)).not.toContain("direwolf");
    expect(typeText("direwolf")).toBe("Packet, sound card, 1200");
  });

  it("is asked for and takes its own sound cards and proposal, never those of the Mercury radio's answer, as every radio with a sound card does", async () => {
    expect(portsAsks([radioRow(1, "kenwood-tnc2"), radioRow(3, "direwolf")])).toEqual([
      { cmd: "list_ports", radio: 3 },
    ]);
    const CODEC = "plughw:CARD=CODEC,DEV=0";
    // the HF radio has its own already
    const empty = {
      ...OWN,
      "radio/2/sound_card": CODEC,
      "radio/2/keying": "rts:/dev/ttyUSB0",
      "radio/3/sound_card": "",
      "radio/3/keying": "",
    };
    const config = configValues({});
    const hfAnswer: PortsMessage = {
      ...ports,
      radio: 2,
      keying: "rts:/dev/ttyUSB0",
      sound_cards: [soundCard(CODEC, "USB Audio CODEC", { pick: true })],
    };
    const daemon = fakeDaemon({
      config: {
        ...config,
        radio_values: { ...config.radio_values, ...empty },
        radio_defaults: { ...config.radio_defaults, ...OWN },
      },
      radios: radiosTopic(
        radioRow(1, "kenwood-tnc2"),
        radioRow(2, "mercury"),
        radioRow(3, "direwolf", { name: "Attic", number: 2, modem: soundCardModem() }),
      ),
      ports: hfAnswer,
      portsByRadio: new Map([[2, hfAnswer]]),
      status: status({ unheard_radio: 1 }),
    });
    const sets = () =>
      daemon.send.mock.calls.filter(([c]) => c.cmd === "set_config").map(([c]) => (c as { values: unknown }).values);
    const wrapper = mount(SettingsForm, {
      props: { scope: "settings" },
      global: withDaemon(daemon),
      attachTo: document.body,
    });
    mounted = wrapper;
    await flushPromises();
    const cards = () =>
      [...wrapper.find<HTMLSelectElement>("#set-radio-3-sound_card").element.options].map((o) => o.value);
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

  it.each([
    ["by its id", "plughw:CARD=FTX1,DEV=0"],
    ["by its number, as an old setting has it", "plughw:1,0"],
  ])(
    "offers first the keying lines of the ports that sit on one USB hub with its sound card, by the order alone, the card stored %s",
    async (_how, stored) => {
      const FTX1 = "plughw:CARD=FTX1,DEV=0";
      const own: PortsMessage = {
        ...ports,
        keying: "",
        sound_cards: [
          soundCard(FTX1, "USB Audio Device", { numbered: "plughw:1,0", usb_group: "ftx1" }),
          soundCard("plughw:CARD=CODEC,DEV=0", "USB Audio CODEC", { usb_group: "other" }),
        ],
        ports: [
          portRow("/dev/ttyUSB0", "CP2105", { usb_group: "other" }),
          portRow("/dev/ttyUSB1", "CP2105", { usb_group: "ftx1" }),
        ],
      };
      const config = configValues({});
      const values = { ...OWN, "radio/3/sound_card": stored, "radio/3/keying": "vox" };
      const daemon = fakeDaemon({
        config: {
          ...config,
          radio_values: { ...config.radio_values, ...values },
          radio_defaults: { ...config.radio_defaults, ...OWN },
        },
        radios: radios(),
        ports: own,
        portsByRadio: new Map([[3, own]]),
        status: status({ unheard_radio: 1 }),
      });
      const wrapper = mount(SettingsForm, {
        props: { scope: "settings" },
        global: withDaemon(daemon),
        attachTo: document.body,
      });
      mounted = wrapper;
      await flushPromises();
      const keying = () =>
        [...wrapper.find<HTMLSelectElement>("#set-radio-3-keying").element.options].map((o) => o.value);
      expect(keying()).toEqual([
        "vox",
        "cm108",
        "rts:/dev/ttyUSB1",
        "dtr:/dev/ttyUSB1",
        "rts:/dev/ttyUSB0",
        "dtr:/dev/ttyUSB0",
        "flrig",
        "rigctld",
      ]);
      // no heading: the order alone
      expect(
        wrapper.find("#set-radio-3-keying").element.closest("fieldset")?.querySelectorAll("optgroup"),
      ).toHaveLength(0);
    },
  );

  it("keyed through rigctld, has an Address row under the keying with the program's own address shown, sent when left, and the Test beside the keying", async () => {
    const config = configValues({});
    const values = { ...OWN, "radio/3/keying": "rigctld" };
    const daemon = fakeDaemon({
      config: {
        ...config,
        radio_values: { ...config.radio_values, ...values },
        radio_defaults: { ...config.radio_defaults, ...OWN },
      },
      radios: radios(),
      ports,
      portsByRadio: new Map([[3, ports]]),
      status: status({ unheard_radio: 1 }),
    });
    const wrapper = mount(SettingsForm, {
      props: { scope: "settings" },
      global: withDaemon(daemon),
      attachTo: document.body,
    });
    mounted = wrapper;
    await flushPromises();
    const address = wrapper.find<HTMLInputElement>("#set-radio-3-keying-address");
    expect(address.exists()).toBe(true);
    expect(address.attributes("placeholder")).toBe("127.0.0.1:4532");
    expect(address.element.value).toBe("");
    expect(address.element.closest(".field")?.querySelector("label")?.textContent).toBe("Address");
    expect(wrapper.find("#set-radio-3-keying-test").exists()).toBe(true);
    await address.setValue("192.168.1.5:4532");
    await address.trigger("keydown.enter");
    expect(daemon.send).toHaveBeenCalledWith({
      cmd: "set_config",
      values: { "radio/3/keying": "rigctld:192.168.1.5:4532" },
    });
  });

  it("has no Address row for a keying by a line, a chip or VOX", async () => {
    const { wrapper } = make();
    mounted = wrapper;
    await flushPromises();
    expect(wrapper.find("#set-radio-3-keying-address").exists()).toBe(false);
  });

  it("says why its modem waits, and has the (i) of its keying, Tune and transmit level, in words of any modem: never Mercury's, the ALC or a steady tone", () => {
    const waiting = (reason: ModemState["reason"]) =>
      rowStatus(
        radioRow(3, "direwolf", { state: "waiting", modem: soundCardModem({ state: "waiting", reason }) }),
        Date.now(),
      );
    const lines = (["not_installed", "network", "not_started", "sound_card", "keying"] as const).map(waiting);
    expect(lines).toEqual([
      "This installation does not carry this radio's modem",
      "Not run: the modem would be open to the network",
      "The modem could not be started",
      "Sound card could not be opened: choose another",
      "Keying device could not be opened: choose another way of keying",
    ]);
    const tips = [
      t("settings.keying.tip1"),
      t("settings.keying.tip2"),
      t("settings.tune.tip1"),
      t("settings.txlevel.tip1"),
    ];
    for (const words of [...lines, ...tips]) expect(words).not.toMatch(/Mercury|ALC|steady/);
  });

  it("says the same in every language of the page: no Mercury, no ALC, no steady tone in any of them", () => {
    // The steady tone as written in each language.
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
        rowStatus(
          radioRow(3, "direwolf", { state: "waiting", modem: soundCardModem({ state: "waiting", reason }) }),
          Date.now(),
        ),
      );
      return [
        ...lines,
        t("settings.keying.tip1"),
        t("settings.keying.tip2"),
        t("settings.tune.tip1"),
        t("settings.txlevel.tip1"),
      ];
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

describe("a Sound card radio's sound on a computer with a sound server", () => {
  const AIOC = "plughw:CARD=AIOC,DEV=0";
  const server: PortsMessage = {
    ...ports,
    sound_cards: [
      ...ports.sound_cards,
      soundCard("pulse:DEVICE=Radio_remap", "Radio", { capture: false }),
      soundCard("pulse:DEVICE=quad_in", "Rubix44", { playback: false }),
      soundCard("pulse:DEVICE=quad_in,CHANNEL=front-left", "Rubix44", { playback: false, channel: 1 }),
      soundCard("pulse:DEVICE=codec_in", "Rubix44", { playback: false }),
    ],
  };

  function mounted3(values: Record<string, string>) {
    const config = configValues({});
    const daemon = fakeDaemon({
      config: {
        ...config,
        radio_values: { ...config.radio_values, ...OWN, ...values },
        radio_defaults: { ...config.radio_defaults, ...OWN },
      },
      radios: radios(),
      ports: server,
      portsByRadio: new Map([[3, server]]),
      status: status({ unheard_radio: 1 }),
    });
    const wrapper = mount(SettingsForm, {
      props: { scope: "settings" },
      global: withDaemon(daemon),
      attachTo: document.body,
    });
    const sets = () =>
      daemon.send.mock.calls.filter(([c]) => c.cmd === "set_config").map(([c]) => (c as { values: unknown }).values);
    return { wrapper, sets };
  }
  const options = (wrapper: ReturnType<typeof mount>, id: string) =>
    [...wrapper.find<HTMLSelectElement>(id).element.options].map((o) => [o.value, o.text]);

  it("chooses what it records from and what it plays to apart, each device by the name the operator gave it", async () => {
    const { wrapper } = mounted3({});
    mounted = wrapper;
    await flushPromises();
    expect(wrapper.find("#set-radio-3-sound_card").exists()).toBe(false);
    expect(options(wrapper, "#set-radio-3-sound_card-capture")).toEqual([
      [AIOC, "All-In-One-Cable"],
      ["pulse:DEVICE=quad_in", "Rubix44"],
      ["pulse:DEVICE=quad_in,CHANNEL=front-left", "Rubix44, channel 1"],
      ["pulse:DEVICE=codec_in", "Rubix44 (2)"],
    ]);
    expect(options(wrapper, "#set-radio-3-sound_card-playback")).toEqual([
      [AIOC, "All-In-One-Cable"],
      ["pulse:DEVICE=Radio_remap", "Radio"],
    ]);
    const labels = wrapper.findAll("label").map((l) => l.text());
    expect(labels).toContain(t("settings.sound_card.capture"));
    expect(labels).toContain(t("settings.sound_card.playback"));
    expect(wrapper.find<HTMLSelectElement>("#set-radio-3-sound_card-capture").element.value).toBe(AIOC);
    expect(wrapper.find<HTMLSelectElement>("#set-radio-3-sound_card-playback").element.value).toBe(AIOC);
    // the row's (i) and Refresh once, not twice
    expect(
      wrapper
        .findAll(".field")
        .filter((f) => f.find("#set-radio-3-sound_card-playback").exists())[0]
        ?.find(".infotip")
        .exists(),
    ).toBe(false);
  });

  it("stores the two as one setting, the device recorded from first", async () => {
    const { wrapper, sets } = mounted3({});
    mounted = wrapper;
    await flushPromises();
    await wrapper.find("#set-radio-3-sound_card-playback").setValue("pulse:DEVICE=Radio_remap");
    await flushPromises();
    expect(sets()).toContainEqual({ "radio/3/sound_card": `${AIOC}|pulse:DEVICE=Radio_remap` });
  });

  it("shows a stored pair in its two fields and a device that is gone by the name the server knew", async () => {
    const { wrapper } = mounted3({
      "radio/3/sound_card": "pulse:DEVICE=quad_in,CHANNEL=front-left|pulse:DEVICE=Radio_gone",
    });
    mounted = wrapper;
    await flushPromises();
    expect(wrapper.find<HTMLSelectElement>("#set-radio-3-sound_card-capture").element.value).toBe(
      "pulse:DEVICE=quad_in,CHANNEL=front-left",
    );
    const playback = wrapper.find<HTMLSelectElement>("#set-radio-3-sound_card-playback").element;
    expect(playback.value).toBe("pulse:DEVICE=Radio_gone");
    expect(playback.options[playback.selectedIndex]?.text).toBe("Radio_gone");
  });
});
