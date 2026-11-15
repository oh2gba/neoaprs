import { describe, expect, it } from "vitest";
import { isOn, mainRadio, pageRadios } from "@/lib/radios";
import { FM_ID, HF_ID, flatRadios, fmOn, hasPaths, hfOn, pageRows, radioFor, stationRadio } from "@/lib/radiosides";
import type { StationRow } from "@/protocol/protocol";
import { configValues, hfState, incoming, message, radioRow, radiosTopic, station, tncState } from "@/test/fixtures";

describe("which radios are on", () => {
  it("has FM on unless the setting says false, as the daemon's default is, and HF off unless it says true", () => {
    const fm: Record<string, string>[] = [{}, { "fm/enabled": "true" }, { "fm/enabled": "false" }, { "fm/enabled": "" }];
    const hf: Record<string, string>[] = [{}, { "hf/enabled": "false" }, { "hf/enabled": "true" }, { "hf/enabled": "" }];
    expect(fm.map((values) => fmOn(values))).toEqual([true, true, false, true]);
    expect(hf.map((values) => hfOn(values))).toEqual([false, false, true, false]);
  });
});

describe("the radio a station is messaged on", () => {
  it("is HF only for a station heard on HF alone, and FM for one heard on FM, on both or on neither", () => {
    const heard = (fm: number, hf: number) => stationRadio(station("OH2XYZ", { heard_fm: fm, heard_hf: hf }));
    expect([heard(3, 0), heard(0, 2), heard(3, 2), heard(0, 0)]).toEqual(["fm", "hf", "fm", "fm"]);
    expect([stationRadio(null), stationRadio(undefined)]).toEqual(["fm", "fm"]);
    expect(stationRadio(station("OH2GAX-2", { heard_fm: 40, heard_hf: 21, message_radio: "hf" }))).toBe("hf");
    expect(stationRadio(station("OH2FAR", { heard_fm: 0, heard_hf: 3, message_radio: "fm" }))).toBe("fm");
  });
});

describe("the path controls", () => {
  const hfOnly = station("OH2HF", { heard_fm: 0, heard_hf: 4 });
  const fm = station("OH2FM", { heard_fm: 4, heard_hf: 0 });

  it("are there for the requests while the FM radio is on, whatever HF does", () => {
    const all: Record<string, string>[] = [
      {},
      { "fm/enabled": "true", "hf/enabled": "true" },
      { "fm/enabled": "false" },
      { "fm/enabled": "false", "hf/enabled": "true" },
    ];
    expect(all.map((values) => hasPaths(values))).toEqual([true, true, false, false]);
  });

  it("are there for a station while FM is on and it is messaged on FM: not when it was heard on HF alone, and for one unknown", () => {
    const on = { "fm/enabled": "true", "hf/enabled": "true" };
    expect([hasPaths(on, fm), hasPaths(on, hfOnly), hasPaths(on, null), hasPaths({ "fm/enabled": "false" }, fm)]).toEqual([true, false, true, false]);
  });
});

describe("the radio a message goes over, as the daemon's table has it", () => {
  const heard = (fm: number, hf: number) => station("OH2XYZ", { heard_fm: fm, heard_hf: hf });
  const cases = [heard(3, 0), heard(0, 2), heard(3, 2), heard(0, 0), null];

  it("is FM for every station while the HF radio is off, whatever was heard", () => {
    for (const values of [{}, { "fm/enabled": "true", "hf/enabled": "false" }] as Record<string, string>[]) {
      expect(cases.map((row) => radioFor(row, values))).toEqual(["fm", "fm", "fm", "fm", "fm"]);
    }
  });

  it("is HF for every station while the FM radio is off", () => {
    expect(cases.map((row) => radioFor(row, { "fm/enabled": "false", "hf/enabled": "true" }))).toEqual(["hf", "hf", "hf", "hf", "hf"]);
  });

  it("is FM for a station heard on FM, on both or on neither, and HF for one heard on HF alone, while both radios are on", () => {
    expect(cases.map((row) => radioFor(row, { "fm/enabled": "true", "hf/enabled": "true" }))).toEqual(["fm", "hf", "fm", "fm", "fm"]);
  });
});

/** radiosides.ts as it was before the page read the topic `radios`: what the views must still give where the daemon does not say otherwise. */
const before = {
  fmOn: (values: Record<string, string>) => values["fm/enabled"] !== "false",
  hfOn: (values: Record<string, string>) => values["hf/enabled"] === "true",
  radioFor(row: StationRow | null, values: Record<string, string>): "fm" | "hf" {
    if (!before.hfOn(values)) return "fm";
    if (!before.fmOn(values)) return "hf";
    if (row?.message_radio === "fm" || row?.message_radio === "hf") return row.message_radio;
    return row != null && row.heard_hf > 0 && row.heard_fm === 0 ? "hf" : "fm";
  },
};
/** A row of a daemon of the wire of before: none of the fields of the radios by id. */
function ofBefore(row: StationRow): StationRow {
  const old: Partial<StationRow> = { ...row };
  for (const key of ["heard", "last_path_radio", "last_direct_any_at", "radio_choice", "radio_now", "paths"] as const) delete old[key];
  return old as StationRow;
}

describe("the views over the radios, against what they gave before", () => {
  const settings: Record<string, string>[] = [
    { "fm/enabled": "true", "hf/enabled": "false" },
    { "fm/enabled": "true", "hf/enabled": "true" },
    { "fm/enabled": "false", "hf/enabled": "true" },
    {},
  ];
  const rows = [
    station("OH2FM", { heard_fm: 3, heard_hf: 0 }),
    station("OH2HF", { heard_fm: 0, heard_hf: 3 }),
    station("OH2BOTH", { heard_fm: 3, heard_hf: 2 }),
    station("OH2NONE", { heard_fm: 0, heard_hf: 0, heard_rf: 0 }),
    station("OH2CHOSE", { heard_fm: 3, heard_hf: 2, message_radio: "hf" }),
    station("OH2OBJ", { kind: "object", can_message: false, heard_fm: 0, heard_hf: 2 }),
  ];

  it("are what they were for one FM radio, for FM and HF and for HF alone, where the daemon's radio is the one the rule of before gives", () => {
    for (const values of settings) {
      const label = JSON.stringify(values);
      expect([fmOn(values), hfOn(values)], label).toEqual([before.fmOn(values), before.hfOn(values)]);
      expect(
        [...rows, null].map((row) => radioFor(row, values)),
        label,
      ).toEqual([...rows, null].map((row) => before.radioFor(row, values)));
      expect(
        [...rows, null].map((row) => hasPaths(values, row)),
        label,
      ).toEqual([...rows, null].map((row) => before.fmOn(values) && before.radioFor(row, values) === "fm"));
      expect(hasPaths(values), label).toBe(before.fmOn(values));
    }
  });

  it("are what they were against a daemon of the wire of before, which says nothing of the radio now", () => {
    for (const values of settings) {
      const old = rows.map(ofBefore);
      expect(
        old.map((row) => radioFor(row, values, [], 2)),
        JSON.stringify(values),
      ).toEqual(old.map((row) => before.radioFor(row, values)));
      expect(radioFor(null, values), JSON.stringify(values)).toBe(before.radioFor(null, values));
    }
  });

  it("take the radio a station is messaged on from the daemon while both radios are on: HF for one FM heard long ago and HF lately, FM for one HF alone heard but chosen FM", () => {
    const on = { "fm/enabled": "true", "hf/enabled": "true" };
    const lately = station("OH2LATE", { heard_fm: 30, heard_hf: 2, radio_now: 2 });
    const chosen = station("OH2FAR", { heard_fm: 0, heard_hf: 3, radio_now: 1 });
    expect([radioFor(lately, on), radioFor(chosen, on)]).toEqual(["hf", "fm"]);
    expect([before.radioFor(lately, on), before.radioFor(chosen, on)]).toEqual(["fm", "hf"]);
    expect([hasPaths(on, lately), hasPaths(on, chosen)]).toEqual([false, true]);
    expect(radioFor(lately, { "fm/enabled": "true", "hf/enabled": "false" })).toBe("fm"); // (the one radio that is on, whatever a row of a moment before says)
  });

  it("take the radio of a message of ours on its way to the station before the station's: the one being sent, else one that waits its turn", () => {
    const on = { "fm/enabled": "true", "hf/enabled": "true" };
    const row = station("OH2RDG", { heard_fm: 3, heard_hf: 2, radio_now: 1 });
    const kept = message(7, { state: "sending", radio_now: 2 });
    expect(radioFor(row, on, [incoming(5, "OH2RDG"), kept])).toBe("hf");
    expect(radioFor(row, on, [message(8, { state: "queued", radio_now: 2 })])).toBe("hf");
    expect(radioFor(row, on, [message(8, { state: "queued", radio_now: 1 }), message(9, { state: "sending", radio_now: 2 })])).toBe("hf");
    expect(radioFor(row, on, [message(6, { state: "acked", radio_now: null }), message(9, { state: "sending", radio_now: null })])).toBe("fm");
    expect(radioFor(row, on, [incoming(5, "OH2RDG", { radio_now: 2 })])).toBe("fm");
    expect(hasPaths(on, row, [kept])).toBe(false);
  });

  it("take the main radio for a call the book does not hold, and FM where the daemon does not name one", () => {
    const on = { "fm/enabled": "true", "hf/enabled": "true" };
    expect([radioFor(null, on, [], 2), radioFor(null, on, [], 1), radioFor(null, on, [], null), radioFor(null, on)]).toEqual(["hf", "fm", "fm", "fm"]);
    expect([hasPaths(on, null, [], 2), hasPaths(on, null, [], 1)]).toEqual([false, true]);
  });

  it("go by the rule of before for a radio they cannot name, a third one", () => {
    const on = { "fm/enabled": "true", "hf/enabled": "true" };
    expect([
      radioFor(station("OH2THREE", { heard_fm: 0, heard_hf: 3, radio_now: 3 }), on),
      radioFor(station("OH2FM3", { heard_fm: 3, radio_now: 3 }), on),
    ]).toEqual(["hf", "fm"]);
    expect(radioFor(null, on, [], 3)).toBe("fm");
  });

  it("leave the channel tags' rule as it was: the radio chosen, else HF for a station heard on HF alone", () => {
    expect(stationRadio(station("OH2LATE", { heard_fm: 30, heard_hf: 2, radio_now: 2 }))).toBe("fm");
    expect(stationRadio(station("OH2FAR", { heard_fm: 0, heard_hf: 3, radio_now: 1 }))).toBe("hf");
  });

  it("take the operator's choice over a message on its way, which goes on the radio chosen from its next attempt: pressing FM shows FM at once", () => {
    const on = { "fm/enabled": "true", "hf/enabled": "true" };
    const pressedFm = station("OH2RDG", { heard_fm: 3, heard_hf: 2, message_radio: "fm" });
    const sending = message(4, { to_call: "OH2RDG", state: "sending", radio: "hf", radio_now: 2 });
    expect([pressedFm.radio_choice, pressedFm.radio_now]).toEqual([1, 1]);
    expect([radioFor(pressedFm, on, [sending]), hasPaths(on, pressedFm, [sending])]).toEqual(["fm", true]);
  });
});

describe("the radios of the settings of before", () => {
  it("are the FM radio as radio 1, on unless it says false, and the HF radio as radio 2, off unless it says true, against a daemon that tells no topic and until it has", () => {
    const settings: Record<string, string>[] = [{}, { "fm/enabled": "false" }, { "hf/enabled": "true" }, { "fm/enabled": "", "hf/enabled": "" }];
    expect(settings.map((values) => [isOn(flatRadios(values), FM_ID), isOn(flatRadios(values), HF_ID)])).toEqual([
      [true, false],
      [false, false],
      [true, true],
      [true, false],
    ]);
    const radios = pageRadios(pageRows(null, configValues({ "hf/enabled": "true" }), null, null), null);
    expect(radios.map((radio) => [radio.id, radio.kind, radio.type, radio.carriesPath, radio.name])).toEqual([
      [1, "fm", "kenwood-tnc2", true, "FM"],
      [2, "hf", "mercury", false, "HF"],
    ]);
    expect(pageRadios(pageRows(null, null, null, null), null).map((radio) => radio.enabled)).toEqual([true, false]);
    expect(mainRadio(flatRadios({ "fm/enabled": "false", "hf/enabled": "true" }), null)?.id).toBe(HF_ID);
    expect(mainRadio(flatRadios({ "fm/enabled": "false" }), null)).toBeNull();
  });

  it("are Dummy radios when their type is, and of the first type of their kind where the settings name none", () => {
    expect(flatRadios({ "tnc/profile": "dummy", "hf/profile": "dummy-hf" }).map((radio) => radio.dummy)).toEqual([true, true]);
    expect(flatRadios({ "tnc/profile": "kiss", "hf/profile": "mercury" }).map((radio) => [radio.type, radio.dummy])).toEqual([
      ["kiss", false],
      ["mercury", false],
    ]);
    expect(flatRadios({}).map((radio) => radio.type)).toEqual(["kenwood-tnc2", "mercury"]);
  });

  it("have the lines of their topics, and why one that is on is not connected", () => {
    const on = { "hf/enabled": "true" };
    const [fm, hf] = flatRadios(on, tncState({ state: "connected" }), hfState({ state: "waiting" })).map((radio) => [
      radio.connected,
      radio.problem?.code ?? null,
      radio.state,
    ]);
    expect([fm, hf]).toEqual([
      [true, null, "connected"],
      [false, "radio.not_connected", "waiting"],
    ]);
    const fmOf = (tnc: ReturnType<typeof tncState> | null) => flatRadios({}, tnc).map((radio) => [radio.problem?.code, radio.state])[0];
    expect([
      fmOf(tncState({ state: "silent", silent_since: "2026-10-21T12:00:00Z" }))?.[0],
      fmOf(tncState({ state: "waiting", searching: ["/dev/ttyUSB0"] }))?.[0],
      ...(fmOf(null) ?? []),
    ]).toEqual(["radio.silent", "radio.searching", "radio.not_connected", "connecting"]);
    const modem = hfState({ state: "waiting" });
    const noModem = flatRadios(on, null, { ...modem, modem: modem.modem && { ...modem.modem, state: "waiting", reason: "not_installed" } })[1];
    expect(noModem?.problem?.code).toBe("modem.not_installed");
    expect(flatRadios({}, null, hfState())[1]?.state).toBe("stopped");
  });

  it("take the Enable of radios 1 and 2 from the settings once the topic is told, where they say it, as the panes of today read it", () => {
    const rows = radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"), radioRow(3, "kiss", { number: 2 }));
    const afterSave = pageRows(rows, configValues({ "hf/enabled": "false" }), null, null);
    expect([...afterSave.values()].map((row) => [row.id, row.enabled, row.state])).toEqual([
      [1, true, "connected"],
      [2, false, "stopped"],
      [3, true, "connected"],
    ]);
    expect(afterSave.get("1")).toBe(rows.get("1"));
    const beforeSettings = pageRows(rows, null, null, null);
    expect(beforeSettings.get("2")?.enabled).toBe(false);
    const after = pageRows(rows, { values: {} }, null, null);
    expect([after.get("1"), after.get("2")]).toEqual([rows.get("1"), rows.get("2")]);
    const removed = radiosTopic(radioRow(2, "mercury", { removed: true, enabled: false }), radioRow(1, "dummy-hf"));
    const kept = pageRows(removed, configValues({ "hf/enabled": "true", "fm/enabled": "false" }), null, null);
    expect([kept.get("2")?.enabled, kept.get("1")?.enabled]).toEqual([false, true]);
  });
});
