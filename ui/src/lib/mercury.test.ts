import { describe, expect, it } from "vitest";
import { keyingChoices, soundCardChoices, soundCardPick, soundCardWith } from "@/lib/mercury";
import type { PortsMessage } from "@/protocol/protocol";

const row = (device: string, description: string) => ({ device, description, hwid: "n/a", vid: null, pid: null });
const ports: PortsMessage = {
  type: "ports",
  search: true,
  find: true,
  ports: [row("/dev/ttyUSB0", "FT232R USB UART"), row("bt://AA:BB:CC:DD:EE:01", "TH-D74"), row("COM3", "USB Serial Port (COM3)")],
  sound_cards: [
    { id: "plughw:1,0", name: "USB Audio CODEC", default: true, pick: true },
    { id: "plughw:0,0", name: "HDA Intel PCH", default: false, pick: false },
  ],
  keying: "rts:/dev/ttyUSB0",
};

describe("the keying choices of the Mercury HF modem", () => {
  it("offer the radio by itself and a CM108 chip, then RTS and DTR of every serial port, never of a Bluetooth device", () => {
    expect(keyingChoices(ports).map((c) => c.value)).toEqual(["vox", "cm108", "rts:/dev/ttyUSB0", "dtr:/dev/ttyUSB0", "rts:COM3", "dtr:COM3"]);
    expect(keyingChoices(ports).map((c) => c.label)).toEqual([
      "The radio keys itself (VOX)",
      "CM108 sound chip",
      "RTS on /dev/ttyUSB0",
      "DTR on /dev/ttyUSB0",
      "RTS on COM3",
      "DTR on COM3",
    ]);
  });

  it("keep the value in force when its port is not listed, and offer the two plain ways before the daemon has listed anything", () => {
    expect(keyingChoices(ports, "dtr:/dev/ttyACM0").map((c) => c.value)).toContain("dtr:/dev/ttyACM0");
    expect(
      keyingChoices(ports, "rts:COM3")
        .map((c) => c.value)
        .filter((v) => v === "rts:COM3"),
    ).toHaveLength(1);
    expect(keyingChoices(null).map((c) => c.value)).toEqual(["vox", "cm108"]);
    expect(keyingChoices(null, "vox").map((c) => c.value)).toEqual(["vox", "cm108"]);
  });
});

describe("the sound cards as a plain choice", () => {
  it("are the cards the daemon listed, the system's name as the label and the id as the hover title, and no choice of leaving it to the daemon", () => {
    const choices = soundCardChoices(ports);
    expect(choices.map((c) => [c.value, c.label, c.title])).toEqual([
      ["plughw:1,0", "USB Audio CODEC", "plughw:1,0"],
      ["plughw:0,0", "HDA Intel PCH", "plughw:0,0"],
    ]);
    expect(choices.map((c) => c.value)).not.toContain("");
    expect(soundCardChoices(null)).toEqual([]);
  });

  it("tell two cards of one name apart by their ids", () => {
    const two: PortsMessage = {
      ...ports,
      sound_cards: [
        { id: "hw:1,0", name: "USB Audio", default: false, pick: false },
        { id: "hw:2,0", name: "USB Audio", default: false, pick: false },
      ],
    };
    expect(soundCardChoices(two).map((c) => c.label)).toEqual(["USB Audio (hw:1,0)", "USB Audio (hw:2,0)"]);
  });

  it("find the whole Windows card of a setting that names one of its two devices, and nothing for a whole card or an unknown one", () => {
    const windows: PortsMessage = {
      ...ports,
      sound_cards: [{ id: "{0.0.1.00000000}.{mic}|{0.0.0.00000000}.{spk}", name: "USB Audio CODEC", default: false, pick: true }],
    };
    expect(soundCardWith(windows, "{0.0.0.00000000}.{spk}")).toBe("{0.0.1.00000000}.{mic}|{0.0.0.00000000}.{spk}");
    expect(soundCardWith(windows, "{0.0.1.00000000}.{mic}")).toBe("{0.0.1.00000000}.{mic}|{0.0.0.00000000}.{spk}");
    expect(soundCardWith(windows, "{0.0.1.00000000}.{mic}|{0.0.0.00000000}.{spk}")).toBe("");
    expect(soundCardWith(windows, "{0.0.0.00000000}.{other}")).toBe("");
    expect(soundCardWith(windows, "")).toBe("");
    expect(soundCardWith(null, "{0.0.0.00000000}.{spk}")).toBe("");
    expect(soundCardWith(ports, "plughw:1,0")).toBe("");
  });

  it("have the daemon's proposal, the one marked, and none before the list is there", () => {
    expect(soundCardPick(ports)).toBe("plughw:1,0");
    expect(soundCardPick({ ...ports, sound_cards: [] })).toBe("");
    expect(soundCardPick(null)).toBe("");
  });
});
