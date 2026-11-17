import { describe, expect, it } from "vitest";
import {
  emailRadio,
  enabledRadios,
  fieldId,
  isNamed,
  isOn,
  messageRadio,
  pageRadio,
  pageRadios,
  problemText,
  radioLabel,
  sameRadio,
  sendingRadio,
  typeOf,
  unheardRadio,
} from "@/lib/radios";
import type { RadioProblem } from "@/protocol/protocol";
import { configValues, heardBy, message, radioRow, radiosTopic as topic, station, status } from "@/test/fixtures";

const ids = (radios: { id: number }[]) => radios.map((radio) => radio.id);

describe("the radios of the topic", () => {
  it("are every radio in the order of their boxes, by position and then by id, a removed one too and never on", () => {
    const rows = topic(
      radioRow(1, "kenwood-tnc2", { position: 2 }),
      radioRow(2, "mercury", { position: 1 }),
      radioRow(4, "kiss", { position: 2, number: 2 }),
      radioRow(3, "dummy", { position: 3, removed: true, enabled: true, number: 3 }),
    );
    const radios = pageRadios(rows, configValues());
    expect(ids(radios)).toEqual([2, 1, 4, 3]);
    expect(radios.map((radio) => [radio.kind, radio.type, radio.enabled, radio.removed, radio.dummy])).toEqual([
      ["hf", "mercury", true, false, false],
      ["fm", "kenwood-tnc2", true, false, false],
      ["fm", "kiss", true, false, false],
      ["fm", "dummy", false, true, true],
    ]);
    expect(ids(enabledRadios(radios))).toEqual([2, 1, 4]);
    expect(radios.map((radio) => radio.row.id)).toEqual([2, 1, 4, 3]);
  });

  it("carry a path where their type allows one", () => {
    const radios = pageRadios(topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"), radioRow(3, "dummy-hf", { number: 2 })), null);
    expect(radios.map((radio) => radio.carriesPath)).toEqual([true, false, false]);
  });

  it("are none when the daemon told none", () => {
    expect(pageRadios(new Map(), configValues())).toEqual([]);
  });

  it("each have their own settings of `radio_values`, by the key of the field", () => {
    const radio2 = { "radio/2/beacon": "true", "radio/2/sound_card": "plughw:1,0", "radio/2/keying": "vox", "radio/2/tx_gain_db": "0" };
    const config = configValues({}, { "radio/1/port": "/dev/ttyUSB0", ...radio2 });
    const [fm, hf] = pageRadios(topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury")), config);
    expect(fm?.settings).toMatchObject({ port: "/dev/ttyUSB0", baud: "9600", beacon: "true" });
    expect(hf?.settings).toEqual({ beacon: "true", sound_card: "plughw:1,0", keying: "vox", tx_gain_db: "0" });
    expect(Object.keys(fm?.settings ?? {})).not.toContain("radio");
  });

  it("say each radio's line: one waiting while another is connected, and none connected that is off or removed", () => {
    const waiting: RadioProblem = { code: "radio.not_connected", params: { name: "FM" } };
    const radios = pageRadios(
      topic(
        radioRow(1, "kenwood-tnc2", { state: "waiting", problem: waiting }),
        radioRow(2, "mercury"),
        radioRow(3, "kiss", { number: 2, enabled: false, state: "connected" }),
        radioRow(4, "kiss", { number: 3, removed: true, state: "connected" }),
      ),
      null,
    );
    expect(radios.map((radio) => [radio.id, radio.state, radio.connected, radio.problem?.code ?? null])).toEqual([
      [1, "waiting", false, "radio.not_connected"],
      [2, "connected", true, null],
      [3, "connected", false, null],
      [4, "connected", false, null],
    ]);
  });

  it("give the row the daemon tells now, while the radio is the same object", () => {
    const first = radioRow(1, "kenwood-tnc2", { stats: { ...radioRow(1, "kenwood-tnc2").stats, packets: 3 } });
    let now = first;
    const radio = pageRadio(now, {}, () => now);
    now = { ...first, stats: { ...first.stats, packets: 7 } };
    expect(radio.row.stats.packets).toBe(7);
    expect(pageRadio(first).row.stats.packets).toBe(3);
  });

  it("are the same radio while only their row's counts, lines or beacon changed", () => {
    const row = radioRow(1, "kenwood-tnc2");
    const was = pageRadio(row);
    expect(sameRadio(was, pageRadio({ ...row, stats: { ...row.stats, packets: 9 }, lines: [{ at: "2026-10-21T12:00:00Z", text: "x" }] }))).toBe(true);
    const changed = [
      { ...row, name: "Shack" },
      { ...row, enabled: false },
      { ...row, state: "waiting" as const },
      { ...row, problem: { code: "radio.searching" as const, params: {} } },
      { ...row, type: "kiss" },
    ];
    expect(changed.map((other) => sameRadio(was, pageRadio(other)))).toEqual([false, false, false, false, false]);
    expect(sameRadio(was, pageRadio(row, { "radio/1/port": "/dev/ttyUSB1" }))).toBe(false);
  });
});

describe("what the page calls a radio", () => {
  it("is the name typed, else the word of its kind, with its number from the second of the kind on", () => {
    expect(radioLabel({ name: "Shack", kind: "fm", number: 2 })).toBe("Shack");
    expect([
      radioLabel({ name: "", kind: "fm", number: 1 }),
      radioLabel({ name: "", kind: "hf", number: 1 }),
      radioLabel({ name: "", kind: "hf", number: 2 }),
    ]).toEqual(["FM", "Mercury", "Mercury 2"]);
    expect(pageRadios(topic(radioRow(5, "dummy-hf", { number: 3 })), null)[0]?.name).toBe("Mercury 3");
  });

  it("makes an element's id of a setting's key", () => {
    expect([fieldId("radio/3/port"), fieldId("email/radio"), fieldId("plain")]).toEqual(["radio-3-port", "email-radio", "plain"]);
  });

  it("has its type as the daemon describes it", () => {
    const [radio] = pageRadios(topic(radioRow(3, "mercury")), null);
    expect(
      radio && [
        typeOf(radio)?.kind,
        typeOf(radio)?.can.tune,
        typeOf(radio)
          ?.fields.map((field) => field.key)
          .sort(),
      ],
    ).toEqual(["hf", true, ["ask", "beacon", "keying", "local_info", "rx_card", "sound_card", "status", "tx_card", "tx_gain_db"]]);
    expect(typeOf({ type: "nonesuch" })).toBeUndefined();
  });
});

describe("what a radio's problem says", () => {
  const said = (code: RadioProblem["code"], params: RadioProblem["params"] = {}) => problemText({ code, params });

  it("is the words of its line's state as the Radio group says them", () => {
    expect([said("radio.not_connected", { name: "FM" }), said("radio.searching"), said("radio.silent", { since: "2026-10-21T12:00:00Z" })]).toEqual([
      "Not connected",
      "Searching for the radio…",
      "silent",
    ]);
  });

  it("is what the modem says of itself for each reason it is not running", () => {
    expect([
      said("modem.not_installed"),
      said("modem.stopped"),
      said("modem.network"),
      said("modem.no_port"),
      said("modem.not_started"),
      said("modem.sound_card"),
    ]).toEqual([
      "This installation does not carry this radio's modem",
      "Not running",
      "Not run: the modem would be open to the network",
      "Not running: no free port",
      "The modem could not be started",
      "Sound card could not be opened: choose another",
    ]);
  });

  it("is the sentence of the refusal for RX only and a beacon not sent, with its reason", () => {
    expect([said("transmit.off"), said("beacon.not_sent", { reason: "no position" })]).toEqual(["RX only: nothing is sent", "nothing was sent: no position"]);
  });

  it("is the sentence of a device another holds where the catalogue has it, else not connected", () => {
    const text = said("radio.resource_held", { resource: "serial", holder: "Mercury" });
    expect(["the device is in use by radio Mercury: choose another", "Not connected"]).toContain(text);
  });
});

describe("the email radio", () => {
  it("is the one the status names, and none where it says none", () => {
    const radios = pageRadios(topic(radioRow(1, "kenwood-tnc2"), radioRow(3, "kiss", { number: 2 })), null);
    expect([emailRadio(radios, status({ email_radio: 3 }))?.id, emailRadio(radios, status({ email_radio: null }))]).toEqual([3, null]);
  });

  it("is any radio the status names that is on and can send: a Mercury radio too", () => {
    const radios = pageRadios(topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"), radioRow(4, "dummy-lora")), null);
    expect([2, 4, 1].map((id) => emailRadio(radios, status({ email_radio: id }))?.id)).toEqual([2, 4, 1]);
  });

  it("is, before the status has come, the first radio that can send in the order of the boxes, of any kind; never one that only listens", () => {
    const radios = pageRadios(
      topic(radioRow(1, "kenwood-tnc2", { removed: true, enabled: false }), radioRow(2, "mercury", { position: 0 }), radioRow(3, "kiss", { number: 1 })),
      null,
    );
    expect([emailRadio(radios, null)?.id, emailRadio(radios, status({ email_radio: 1 }))?.id]).toEqual([2, 2]);
    expect(emailRadio(pageRadios(topic(radioRow(1, "mercury", { position: 1 }), radioRow(2, "kiss", { position: 2 })), null), null)?.id).toBe(1);
    expect(emailRadio(pageRadios(topic(radioRow(2, "mercury")), null), null)?.id).toBe(2);
    expect(
      emailRadio(pageRadios(topic(radioRow(5, "tnc-text", { position: 0 }), radioRow(2, "mercury"), radioRow(6, "dummy-hf", { number: 2 })), null), null)?.id,
    ).toBe(2);
    expect(emailRadio(pageRadios(topic(radioRow(5, "tnc-text")), null), null)).toBeNull();
  });
});

describe("the radio of a call no radio heard", () => {
  const boxes = pageRadios(
    topic(
      radioRow(5, "tnc-text", { position: 0, number: 2 }),
      radioRow(2, "mercury", { position: 1 }),
      radioRow(1, "kenwood-tnc2", { position: 2 }),
      radioRow(4, "kiss", { position: 3, enabled: false, number: 3 }),
    ),
    null,
  );

  it("is the one the status names, and none where it says none", () => {
    expect([unheardRadio(boxes, status({ unheard_radio: 1 }))?.id, unheardRadio(boxes, status({ unheard_radio: null }))]).toEqual([1, null]);
  });

  it("is, before the status has come, the first radio that is on and can send, in the order of the boxes: never one that only listens, is off or is not there", () => {
    expect([
      unheardRadio(boxes, null)?.id,
      unheardRadio(boxes, status({ unheard_radio: 4 }))?.id,
      unheardRadio(boxes, status({ unheard_radio: 5 }))?.id,
    ]).toEqual([2, 2, 2]);
    expect(unheardRadio(pageRadios(topic(radioRow(5, "tnc-text")), null), null)).toBeNull();
  });

  it("is the radio a message to a call the book does not hold goes on", () => {
    expect([sendingRadio(null, [], 2), sendingRadio(null, [{ state: "sending", radio_now: 1 }], 2), sendingRadio(null)]).toEqual([2, 1, null]);
  });
});

describe("whether a radio is named", () => {
  it("is so where more than one radio is on, and always for a radio that is not on", () => {
    const one = pageRadios(
      topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false }), radioRow(3, "kiss", { removed: true, enabled: false })),
      null,
    );
    expect([isNamed(one, 1), isNamed(one, 2), isNamed(one, 3), isNamed(one, 9)]).toEqual([false, true, true, true]);
    const two = pageRadios(topic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury")), null);
    expect([isNamed(two, 1), isNamed(two, 2)]).toEqual([true, true]);
    expect([isOn(two, 2), isOn(one, 2)]).toEqual([true, false]);
  });
});

describe("the radio a message to a station goes on", () => {
  const row = station("OH2RDG", { heard: heardBy([1, 3], [2, 2, null]), radio_now: 1 });

  it("is the station's radio now, any radio by its id", () => {
    expect([sendingRadio(row), sendingRadio({ ...row, radio_now: 3 }), sendingRadio({ ...row, radio_now: null })]).toEqual([1, 3, null]);
  });

  it("is that of a message of ours on its way to it, the one being sent before one that waits its turn", () => {
    expect(sendingRadio(row, [message(7, { state: "queued", radio_now: 3 }), message(8, { state: "sending", radio_now: 2 })])).toBe(2);
    expect(sendingRadio(row, [message(7, { state: "queued", radio_now: 3 })])).toBe(3);
    expect(sendingRadio(row, [message(7, { state: "acked" }), message(8, { direction: "in", state: "received", radio_now: 2 })])).toBe(1);
  });

  it("is the operator's choice while it is in force, also over a message on its way, which takes it from its next attempt", () => {
    const chosen = station("OH2RDG", { heard: heardBy([1, 3], [2, 2, null]), radio_choice: 1, radio_now: 1 });
    expect(sendingRadio(chosen, [message(8, { state: "sending", radio_now: 2 })])).toBe(1);
    expect(sendingRadio({ ...chosen, radio_choice: 3, radio_now: 3 }, [message(8, { state: "queued", radio_now: 1 })])).toBe(3);
  });

  it("is the radio of a call no radio heard for a call the book does not hold, and none where there is none", () => {
    expect([sendingRadio(null, [], 3), sendingRadio(undefined, [], 2), sendingRadio(null)]).toEqual([3, 2, null]);
    expect(sendingRadio(null, [message(8, { state: "sending", radio_now: 4 })], 3)).toBe(4);
  });

  it("is none against a daemon that does not say", () => {
    expect(sendingRadio({}, [{ state: "sending" }])).toBeNull();
  });
});

describe("the radio of a message", () => {
  it("is the one its next attempt goes on while it is on its way, else the one it came or went on", () => {
    expect([
      messageRadio(message(1, { state: "sending", radio_id: 1, radio_now: 3 })),
      messageRadio(message(2, { state: "acked", radio_id: 2 })),
      messageRadio(message(3, { state: "acked" })),
      messageRadio({ radio_id: 4, radio_now: null }),
    ]).toEqual([3, 2, null, 4]);
  });
});
