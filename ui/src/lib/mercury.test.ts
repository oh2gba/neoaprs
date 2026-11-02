import { describe, expect, it } from "vitest";
import { keyingChoices, soundCardPorts } from "@/lib/mercury";
import type { PortsMessage } from "@/protocol/protocol";

const row = (device: string, description: string) => ({ device, description, hwid: "n/a", vid: null, pid: null });
const ports: PortsMessage = {
  type: "ports",
  search: true,
  find: true,
  ports: [row("/dev/ttyUSB0", "FT232R USB UART"), row("bt://AA:BB:CC:DD:EE:01", "TH-D74"), row("COM3", "USB Serial Port (COM3)")],
  sound_cards: [
    { id: "plughw:1,0", name: "USB Audio CODEC", default: true },
    { id: "plughw:0,0", name: "HDA Intel PCH", default: false },
  ],
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

describe("the sound cards as a list like the ports", () => {
  it("are the cards the daemon listed, the id as the device and the system's name as its description, and nothing is searched for", () => {
    const cards = soundCardPorts(ports);
    expect(cards?.ports.map((p) => [p.device, p.description])).toEqual([
      ["plughw:1,0", "USB Audio CODEC"],
      ["plughw:0,0", "HDA Intel PCH"],
    ]);
    expect(cards?.search).toBe(false);
    expect(soundCardPorts(null)).toBeNull();
  });
});
