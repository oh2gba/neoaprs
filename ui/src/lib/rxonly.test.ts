// A radio of a type that only listens (`tnc-text`: a Yaesu FTM, a TNC that prints what it hears): it is in no list of the radios to send on, and while it is the only kind of radio on, the header says RX only
// with a title of its own, and the page is receive only as with RX only ticked.
import { describe, expect, it } from "vitest";
import { t } from "@/i18n";
import { headerPills } from "@/lib/pills";
import { listensOnly, pageRadios, senders } from "@/lib/radios";
import { RADIO_TYPES } from "@/protocol/lists";
import { fakeDaemon } from "@/test/context";
import { configValues, radioRow, radiosTopic } from "@/test/fixtures";

describe("a radio that only listens", () => {
  it("is of one of the two types that cannot send (the TNC's text and the LoRa iGate's log), and has no beacon tick, no path and no digipeater", () => {
    expect(RADIO_TYPES.filter((type) => !type.can.transmit).map((type) => type.key)).toEqual(["tnc-text", "lora-console"]);
    const text = RADIO_TYPES.find((type) => type.key === "tnc-text");
    expect(text?.fields.map((field) => field.key)).toEqual(["port", "baud"]);
    expect(text?.allowed).toEqual({ paths: false, digipeat: false, smart_beacon: false, gateway_heard: false, shared_channel: false });
  });

  it("is on and is no radio to send on", () => {
    const rows = radiosTopic(radioRow(1, "tnc-text"), radioRow(2, "mercury", { enabled: false }), radioRow(3, "dummy"));
    expect(senders(pageRadios(rows, configValues())).map((radio) => radio.id)).toEqual([3]);
    expect(listensOnly(rows)).toBe(false);
  });

  it("alone makes the station receive only, and the header says so by the radios, not by the RX only tick", () => {
    const rows = radiosTopic(radioRow(1, "tnc-text"), radioRow(2, "mercury", { enabled: false }), radioRow(3, "kiss", { removed: true, enabled: false }));
    expect(listensOnly(rows)).toBe(true);
    expect(listensOnly(radiosTopic(radioRow(1, "tnc-text", { enabled: false })))).toBe(false);
    expect(listensOnly(null)).toBe(false);
    const rx = (values: Record<string, string>, listening: boolean) =>
      headerPills(values, null, null, null, null, null, listening).find((pill) => pill.id === "rx");
    expect(rx({}, true)).toMatchObject({ text: "pill.rx", title: "pill.rx_title_radios", tone: "warn", target: "settings" });
    expect(t("pill.rx_title_radios")).toBe("Nothing is sent. Settings → Radio");
    expect(rx({ "station/transmit": "false" }, true)?.title).toBe("pill.rx_title");
    expect(rx({}, false)).toBeUndefined();
  });

  it("alone leads the RX only mark to the box of the first radio that is on, where its type is chosen, and the RX only tick to the tick", () => {
    const rows = radiosTopic(radioRow(1, "kiss", { enabled: false }), radioRow(3, "tnc-text"), radioRow(4, "lora-console"));
    const link = { connection: "open", now: 0, inApp: false, told: true, radios: pageRadios(rows, configValues()) } as const;
    const rx = (values: Record<string, string>) => headerPills(values, null, null, null, link, null, listensOnly(rows)).find((pill) => pill.id === "rx");
    expect(rx({})?.focus).toBe("set-radio-3-enabled");
    expect(rx({ "station/transmit": "false" })?.focus).toBe("set-station-transmit");
  });

  it("alone makes a pane's test context receive only, as the shell is", () => {
    expect(fakeDaemon({ radios: radiosTopic(radioRow(1, "tnc-text")) }).receiveOnly.value).toBe(true);
    expect(fakeDaemon({ radios: radiosTopic(radioRow(1, "tnc-text"), radioRow(3, "dummy")) }).receiveOnly.value).toBe(false);
    expect(fakeDaemon().receiveOnly.value).toBe(false);
  });
});
