// A radio type that only listens (`tnc-text`, e.g. a TNC that prints what it hears) is in no list
// of radios to send on. While it is the only radio on, the RX only switch says RX only with its
// own title and the page is receive-only, as with RX only switched on.
import { describe, expect, it } from "vitest";
import { t } from "@/i18n";
import { headerPills } from "@/lib/pills";
import { listensOnly, pageRadios, senders } from "@/lib/radios";
import { RADIO_TYPES } from "@/protocol/lists";
import { fakeDaemon } from "@/test/context";
import { configValues, radioRow, radiosTopic } from "@/test/fixtures";

describe("a radio that only listens", () => {
  it("is of one of the two types that cannot send (the TNC's text and the LoRa iGate's log), and has no beacon tick, no path and no digipeater", () => {
    expect(RADIO_TYPES.filter((type) => !type.can.transmit).map((type) => type.key)).toEqual([
      "tnc-text",
      "lora-console",
    ]);
    const text = RADIO_TYPES.find((type) => type.key === "tnc-text");
    expect(text?.fields.map((field) => field.key)).toEqual(["port", "baud"]);
    expect(text?.allowed).toEqual({
      paths: false,
      digipeat: false,
      smart_beacon: false,
      gateway_heard: false,
      shared_channel: false,
    });
  });

  it("is on and is no radio to send on", () => {
    const rows = radiosTopic(radioRow(1, "tnc-text"), radioRow(2, "mercury", { enabled: false }), radioRow(3, "dummy"));
    expect(senders(pageRadios(rows, configValues())).map((radio) => radio.id)).toEqual([3]);
    expect(listensOnly(rows)).toBe(false);
  });

  it("alone makes the station receive only; the RX only switch says so (lib/rxswitch.test.ts), no mark does", () => {
    const rows = radiosTopic(
      radioRow(1, "tnc-text"),
      radioRow(2, "mercury", { enabled: false }),
      radioRow(3, "kiss", { removed: true, enabled: false }),
    );
    expect(listensOnly(rows)).toBe(true);
    expect(listensOnly(radiosTopic(radioRow(1, "tnc-text", { enabled: false })))).toBe(false);
    expect(listensOnly(null)).toBe(false);
    const link = {
      connection: "open",
      now: 0,
      inApp: false,
      told: true,
      radios: pageRadios(rows, configValues()),
    } as const;
    const ids = headerPills({ "station/transmit": "false" }, null, null, null, link).map((pill): string => pill.id);
    expect(ids).toEqual(["daemon", "radio"]);
    expect(t("pill.rx_title_radios")).toBe("Nothing is sent. Settings → Radio");
  });

  it("alone makes a pane's test context receive only, as the shell is", () => {
    expect(fakeDaemon({ radios: radiosTopic(radioRow(1, "tnc-text")) }).receiveOnly.value).toBe(true);
    expect(fakeDaemon({ radios: radiosTopic(radioRow(1, "tnc-text"), radioRow(3, "dummy")) }).receiveOnly.value).toBe(
      false,
    );
    expect(fakeDaemon().receiveOnly.value).toBe(false);
  });
});
