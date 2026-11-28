import { describe, expect, it } from "vitest";
import { portRow, soundCard } from "@/test/fixtures";
import {
  keyingChoices,
  rigAddress,
  rigDefault,
  rigKind,
  soundCardChoices,
  soundCardHalfChoices,
  soundCardPick,
  soundCardWith,
  withAddress,
} from "@/lib/mercury";
import { holderOf } from "@/lib/portchoice";
import type { PortsMessage } from "@/protocol/protocol";

const row = (device: string, description: string) => portRow(device, description);
const ports: PortsMessage = {
  type: "ports",
  search: true,
  find: true,
  ports: [
    row("/dev/ttyUSB0", "FT232R USB UART"),
    row("bt://AA:BB:CC:DD:EE:01", "TH-D74"),
    row("COM3", "USB Serial Port (COM3)"),
  ],
  sound_cards: [
    soundCard("plughw:1,0", "USB Audio CODEC", { default: true, pick: true }),
    soundCard("plughw:0,0", "HDA Intel PCH", { default: false, pick: false }),
  ],
  keying: "rts:/dev/ttyUSB0",
  radio: 2,
};

describe("the keying choices of the Mercury modem", () => {
  it("offer the radio by itself and a CM108 chip, then RTS and DTR of every serial port, never of a Bluetooth device", () => {
    expect(keyingChoices(ports).map((c) => c.value)).toEqual([
      "vox",
      "cm108",
      "rts:/dev/ttyUSB0",
      "dtr:/dev/ttyUSB0",
      "rts:COM3",
      "dtr:COM3",
      "flrig",
      "rigctld",
    ]);
    expect(keyingChoices(ports).map((c) => c.label)).toEqual([
      "The radio keys itself (VOX)",
      "CM108 sound chip",
      "RTS on /dev/ttyUSB0",
      "DTR on /dev/ttyUSB0",
      "RTS on COM3",
      "DTR on COM3",
      "flrig",
      "rigctld",
    ]);
  });

  it("keep the value in force when its port is not listed, and offer the two plain ways before the daemon has listed anything", () => {
    expect(keyingChoices(ports, "dtr:/dev/ttyACM0").map((c) => c.value)).toContain("dtr:/dev/ttyACM0");
    expect(
      keyingChoices(ports, "rts:COM3")
        .map((c) => c.value)
        .filter((v) => v === "rts:COM3"),
    ).toHaveLength(1);
    expect(keyingChoices(null).map((c) => c.value)).toEqual(["vox", "cm108", "flrig", "rigctld"]);
    expect(keyingChoices(null, "vox").map((c) => c.value)).toEqual(["vox", "cm108", "flrig", "rigctld"]);
  });
});

describe("keying through a rig program the operator runs", () => {
  it("is offered after the lines, and the choice in force keeps its address", () => {
    const values = keyingChoices(ports, "rigctld:10.0.0.2:4532").map((c) => c.value);
    expect(values.slice(-2)).toEqual(["flrig", "rigctld:10.0.0.2:4532"]);
    expect(
      keyingChoices(ports, "flrig")
        .map((c) => c.value)
        .slice(-2),
    ).toEqual(["flrig", "rigctld"]);
  });

  it("is told by its kind, its address is what follows, and an empty address is the program's own", () => {
    expect([rigKind("flrig"), rigKind("RIGCTLD:host:1"), rigKind("rts:COM3"), rigKind("")]).toEqual([
      "flrig",
      "rigctld",
      "",
      "",
    ]);
    expect([rigAddress("flrig"), rigAddress("rigctld:10.0.0.2:4532"), rigAddress("flrig:[::1]:12345")]).toEqual([
      "",
      "10.0.0.2:4532",
      "[::1]:12345",
    ]);
    expect([withAddress("flrig", " 10.0.0.2:12345 "), withAddress("rigctld", "")]).toEqual([
      "flrig:10.0.0.2:12345",
      "rigctld",
    ]);
    expect([rigDefault("flrig"), rigDefault("rigctld")]).toEqual(["127.0.0.1:12345", "127.0.0.1:4532"]);
  });
});

describe("the keying choices of a radio whose sound card sits on one USB hub with serial ports", () => {
  const two: PortsMessage = {
    ...ports,
    ports: [
      portRow("/dev/ttyUSB0", "CP2105 Dual USB to UART Bridge Controller", { usb_group: "other" }),
      portRow("/dev/ttyUSB1", "CP2105 Dual USB to UART Bridge Controller", { usb_group: "ftx1" }),
      portRow("/dev/ttyS0", "ttyS0"),
      portRow("/dev/ttyUSB2", "CP2102 USB to UART Bridge Controller", { usb_group: "ftx1" }),
    ],
  };

  it("offer the lines of the ports with the card first, the others after in the daemon's order, and nothing else changes", () => {
    expect(keyingChoices(two, "", "ftx1").map((c) => c.value)).toEqual([
      "vox",
      "cm108",
      "rts:/dev/ttyUSB1",
      "dtr:/dev/ttyUSB1",
      "rts:/dev/ttyUSB2",
      "dtr:/dev/ttyUSB2",
      "rts:/dev/ttyUSB0",
      "dtr:/dev/ttyUSB0",
      "rts:/dev/ttyS0",
      "dtr:/dev/ttyS0",
      "flrig",
      "rigctld",
    ]);
    expect(keyingChoices(two, "", "ftx1")[2]?.label).toBe("RTS on /dev/ttyUSB1"); // same words: no heading, no mark
    const plain = keyingChoices(two).map((c) => c.value);
    expect(keyingChoices(two, "", null).map((c) => c.value)).toEqual(plain);
    expect(keyingChoices(two, "", "none of them").map((c) => c.value)).toEqual(plain);
    expect(new Set(keyingChoices(two, "", "ftx1").map((c) => c.value))).toEqual(new Set(plain));
  });
});

describe("a sound server's devices with long descriptions", () => {
  it("are shortened in the middle, so the device's name at the start and the way at the end stay in a phone's field", () => {
    const long: PortsMessage = {
      ...ports,
      sound_cards: [
        soundCard("pulse:DEVICE=ftdx_in", "FTDX101 USB Audio CODEC Analog Stereo Input", { playback: false }),
        soundCard("pulse:DEVICE=ftdx_out", "FTDX101 USB Audio CODEC Analog Stereo Output", { capture: false }),
        soundCard(
          "pulse:DEVICE=scarlett_in",
          "Scarlett 2i2 4th Gen USB Audio Analog Stereo Input (Focusrite Digital Audio Interface)",
          { playback: false },
        ),
        soundCard("pulse:DEVICE=quad_in", "Rubix44 Pro (4 channels, USB Audio Class 2)", { playback: false }),
        soundCard("pulse:DEVICE=radio", "Radio", { capture: false }),
      ],
    };
    const capture = soundCardHalfChoices(long, "capture").map((c) => c.label);
    const playback = soundCardHalfChoices(long, "playback").map((c) => c.label);
    expect(capture).toEqual(["FTDX101 USB…Stereo Input", "Scarlett 2i2…Stereo Input", "Rubix44 Pro"]);
    expect(playback).toEqual(["FTDX101 USB…Stereo Output", "Radio"]);
    for (const label of [...capture, ...playback]) expect(label.length, label).toBeLessThanOrEqual(26);
  });
});

describe("the sound cards as a plain choice", () => {
  it("are the cards the daemon listed, the system's name as the label and no hover title, and no choice of leaving it to the daemon", () => {
    const choices = soundCardChoices(ports);
    expect(choices.map((c) => [c.value, c.label, c.title])).toEqual([
      ["plughw:1,0", "USB Audio CODEC", undefined],
      ["plughw:0,0", "HDA Intel PCH", undefined],
    ]);
    expect(choices.map((c) => c.value)).not.toContain("");
    expect(soundCardChoices(null)).toEqual([]);
  });

  it("tell two cards of one name apart by their ids", () => {
    const two: PortsMessage = {
      ...ports,
      sound_cards: [
        soundCard("hw:1,0", "USB Audio", { default: false, pick: false }),
        soundCard("hw:2,0", "USB Audio", { default: false, pick: false }),
      ],
    };
    expect(soundCardChoices(two).map((c) => c.label)).toEqual(["USB Audio (hw:1,0)", "USB Audio (hw:2,0)"]);
  });

  it("grey a card another radio holds, with its name, but not in that radio's own box nor the card in force", () => {
    const held: PortsMessage = {
      ...ports,
      radio: 3,
      sound_cards: [
        soundCard("plughw:1,0", "USB Audio CODEC", { held_by: 2 }),
        soundCard("plughw:0,0", "HDA Intel PCH", { pick: true }),
      ],
    };
    const names = (id: number) => ({ 2: "20 m" })[id];
    expect(soundCardChoices(held, holderOf(3, names)).map((c) => [c.label, c.disabled ?? false])).toEqual([
      ["20 m: USB Audio CODEC", true],
      ["HDA Intel PCH", false],
    ]);
    expect(soundCardChoices(held, holderOf(2, names)).map((c) => c.disabled ?? false)).toEqual([false, false]);
    expect(soundCardChoices(held, holderOf(3, names), "plughw:1,0").map((c) => c.disabled ?? false)).toEqual([
      false,
      false,
    ]);
  });

  it("find the whole Windows card of a setting that names one of its two devices, and nothing for a whole card or an unknown one", () => {
    const windows: PortsMessage = {
      ...ports,
      sound_cards: [
        soundCard("{0.0.1.00000000}.{mic}|{0.0.0.00000000}.{spk}", "USB Audio CODEC", { default: false, pick: true }),
      ],
    };
    expect(soundCardWith(windows, "{0.0.0.00000000}.{spk}")).toBe("{0.0.1.00000000}.{mic}|{0.0.0.00000000}.{spk}");
    expect(soundCardWith(windows, "{0.0.1.00000000}.{mic}")).toBe("{0.0.1.00000000}.{mic}|{0.0.0.00000000}.{spk}");
    expect(soundCardWith(windows, "{0.0.1.00000000}.{mic}|{0.0.0.00000000}.{spk}")).toBe("");
    expect(soundCardWith(windows, "{0.0.0.00000000}.{other}")).toBe("");
    expect(soundCardWith(windows, "")).toBe("");
    expect(soundCardWith(null, "{0.0.0.00000000}.{spk}")).toBe("");
    expect(soundCardWith(ports, "plughw:1,0")).toBe("");
    const linux: PortsMessage = {
      ...ports,
      sound_cards: [
        soundCard("plughw:CARD=Device,DEV=0", "USB Audio Device", {
          numbered: "plughw:0,0",
          default: false,
          pick: false,
        }),
        soundCard("plughw:CARD=CODEC,DEV=0", "USB AUDIO  CODEC", {
          numbered: "plughw:3,0",
          default: false,
          pick: true,
        }),
      ],
    };
    expect(soundCardWith(linux, "plughw:3,0")).toBe("plughw:CARD=CODEC,DEV=0");
    expect(soundCardWith(linux, "plughw:0,0")).toBe("plughw:CARD=Device,DEV=0");
    expect(soundCardWith(linux, "plughw:CARD=CODEC,DEV=0")).toBe("");
    expect(soundCardWith(linux, "plughw:5,0")).toBe("");
  });

  it("have the daemon's proposal, the one marked, and none before the list is there", () => {
    expect(soundCardPick(ports)).toBe("plughw:1,0");
    expect(soundCardPick({ ...ports, sound_cards: [] })).toBe("");
    expect(soundCardPick(null)).toBe("");
  });
});
