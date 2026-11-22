// The RX only switch's face and press for the setting, the radios that can send and the socket.
import { describe, expect, it } from "vitest";
import { listensOnly, pageRadios } from "@/lib/radios";
import { rxSwitch } from "@/lib/rxswitch";
import { configValues, radioRow, radiosTopic } from "@/test/fixtures";

describe("the RX only switch", () => {
  it("is RX + TX and a toggle while the station transmits, RX only and a toggle while station/transmit is false", () => {
    expect(rxSwitch("true", false, "open", undefined)).toEqual({
      face: "tx",
      act: "toggle",
      title: "header.rx.tx_title",
      focus: "",
    });
    expect(rxSwitch("false", false, "open", undefined)).toEqual({
      face: "rx",
      act: "toggle",
      title: "header.rx.rx_title",
      focus: "",
    });
  });

  it("is RX only and leads to the first radio's box while no radio that is on can send, and a toggle again once the setting is false", () => {
    const rows = radiosTopic(
      radioRow(1, "kiss", { enabled: false }),
      radioRow(3, "tnc-text"),
      radioRow(4, "lora-console"),
    );
    const first = pageRadios(rows, configValues()).filter((radio) => radio.enabled)[0];
    const listening = listensOnly(rows);
    expect(listening).toBe(true);
    // the four of listening and the setting
    expect(rxSwitch("true", listening, "open", first)).toEqual({
      face: "rx",
      act: "open",
      title: "pill.rx_title_radios",
      focus: "set-radio-3-enabled",
    });
    expect(rxSwitch("false", listening, "open", first)).toMatchObject({ face: "rx", act: "toggle" });
    expect(rxSwitch("false", false, "open", first)).toMatchObject({ face: "rx", act: "toggle" });
    expect(rxSwitch("true", false, "open", first)).toMatchObject({ face: "tx", act: "toggle" });
    expect(rxSwitch("true", true, "open", undefined).focus).toBe("set-radio-add");
  });

  it("is no toggle while the socket is connecting or closed, with the Daemon mark's title, and keeps the face it had", () => {
    expect(rxSwitch("true", false, "connecting", undefined)).toMatchObject({
      face: "tx",
      act: "none",
      title: "pill.daemon_connecting_title",
    });
    expect(rxSwitch("false", false, "closed", undefined)).toMatchObject({
      face: "rx",
      act: "none",
      title: "pill.daemon_offline_title",
    });
    expect(rxSwitch("true", true, "closed", undefined)).toMatchObject({ face: "rx", act: "none" });
  });
});
