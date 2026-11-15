import { describe, expect, it } from "vitest";
import {
  anyInternet,
  channelsOf,
  heardParts,
  heardTags,
  heardTimes,
  heardWords,
  internetOnly,
  onAir,
  packetCameBy,
  packetChannel,
  packetLabel,
  packetTag,
  radioTone,
} from "@/lib/channels";
import { pageRadios } from "@/lib/radios";
import type { RadioRow, StationRow } from "@/protocol/protocol";
import { NOW, ago, heardBy, packet, radioRow, radiosTopic, station } from "@/test/fixtures";

const radiosOf = (...rows: RadioRow[]) => pageRadios(radiosTopic(...rows), null);
const FM = radioRow(1, "kenwood-tnc2");
const HF = radioRow(2, "mercury");
const HF_OFF = radioRow(2, "mercury", { enabled: false, state: "stopped" });
/** The station of today: the FM radio on, the HF radio off. */
const ONE = radiosOf(FM, HF_OFF);
/** The owner's station: both on. */
const TWO = radiosOf(FM, HF);
/** The HF radio alone. */
const HF_ALONE = radiosOf(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), HF);
/** Six radios on: two of them named, two Dummies (one of them named); a LoRa one has its own tests below. */
const SIX = radiosOf(
  FM,
  HF,
  radioRow(3, "kiss", { name: "Shack", number: 2 }),
  radioRow(4, "dummy-hf", { name: "20 m", number: 2 }),
  radioRow(5, "kantronics", { number: 3 }),
  radioRow(6, "dummy", { number: 4 }),
);

/** The words of a row's tags joined, as the table shows them side by side. */
const labels = (row: StationRow, radios = ONE) =>
  heardTags(row, radios, NOW)
    .map((tag) => tag.label)
    .join(" · ");
const titles = (row: StationRow, radios = ONE) =>
  heardTags(row, radios, NOW)
    .map((tag) => tag.title)
    .join("; ");

const rf = station("RF", { heard_rf: 3, heard_rf_gated: 0, heard_is: 0 });
const gated = station("GATED", { heard_rf: 0, heard_rf_gated: 2, heard_is: 0 });
const net = station("NET", { heard_rf: 0, heard_rf_gated: 0, heard_is: 4, last_rf_at: null, last_is_at: ago(40), position_via: "is" });
const both = station("BOTH", { heard_rf: 3, heard_rf_gated: 0, heard_is: 1, last_rf_at: ago(180), last_is_at: ago(40) });
const all = station("ALL", { heard_rf: 1, heard_rf_gated: 1, heard_is: 1, last_rf_at: ago(60), last_rf_gated_at: ago(120), last_is_at: ago(30) });
const none = station("OH2GBA", { is_me: true, heard_rf: 0, heard_rf_gated: 0, heard_is: 0 });

describe("the channels a station was heard by", () => {
  it("are RF, iGate and Internet, in that order, for the counts that are not zero", () => {
    expect([rf, gated, net, both, all].map(channelsOf)).toEqual([["rf"], ["gated"], ["is"], ["rf", "is"], ["rf", "gated", "is"]]);
  });

  it("are none for our own station and our objects, which are not heard, whatever a count says", () => {
    expect(channelsOf(none)).toEqual([]);
    expect(channelsOf({ ...rf, is_me: true })).toEqual([]);
    expect(channelsOf({ ...rf, own: true })).toEqual([]);
    expect(heardTags({ ...rf, own: true }, ONE, NOW)).toEqual([]);
  });

  it("make the small tags of a row: one word, or two or three side by side", () => {
    expect([rf, gated, net, both, all, none].map((row) => labels(row))).toEqual(["RF", "iGate", "Internet", "RF · Internet", "RF · iGate · Internet", ""]);
  });

  it("have a title that says what each word means", () => {
    expect(titles(rf)).toBe("Heard on the radio");
    expect(titles(gated)).toBe("Heard on the radio from an iGate, which took it from the internet");
    expect(titles(net)).toBe("Received over the internet (APRS-IS), not on the radio");
    expect(titles(both)).toBe("Heard on the radio; Received over the internet (APRS-IS), not on the radio");
    expect(titles(none)).toBe("");
  });

  it("are told with when each was last heard: RF 3 min ago · Internet 40 s ago", () => {
    expect(heardTimes(both, ONE, NOW)).toBe("RF 3 min ago · Internet 40 s ago");
    expect(heardTimes(rf, ONE, NOW)).toBe("RF 1 min ago");
    expect(heardTimes(all, ONE, NOW)).toBe("RF 1 min ago · iGate 2 min ago · Internet 30 s ago");
    expect(heardTimes(none, ONE, NOW)).toBe("");
  });

  it("are the channels of before against a daemon that does not count by radio", () => {
    const before = (row: StationRow): StationRow => {
      const copy: Partial<StationRow> = { ...row };
      delete copy.heard;
      return copy as StationRow;
    };
    expect([rf, both, all].map((row) => labels(before(row)))).toEqual(["RF", "RF · Internet", "RF · iGate · Internet"]);
    expect(heardTimes(before(both), ONE, NOW)).toBe("RF 3 min ago · Internet 40 s ago");
  });
});

describe("a station of the Dummy radio", () => {
  const dummy = station("QDUMMY-1", { heard_rf: 0, heard_dummy: 3, last_rf_at: null, last_dummy_at: ago(90) });
  const DUMMY = radiosOf(radioRow(1, "dummy"), HF_OFF);

  it("is labelled Dummy, joined to the others, told by its own time, and is on the air for everything but the internet", () => {
    expect(channelsOf(dummy)).toEqual(["dummy"]);
    expect(labels(dummy)).toBe("Dummy");
    expect(labels(dummy, DUMMY)).toBe("Dummy");
    expect(labels({ ...dummy, heard_rf: 1 })).toBe("RF · Dummy");
    expect(titles(dummy, DUMMY)).toBe("Made up by the Dummy radio, which is no real radio");
    expect(heardTimes(dummy, DUMMY, NOW)).toBe("Dummy 1 min ago");
    expect(heardTags(dummy, DUMMY, NOW).map((tag) => tag.tone)).toEqual(["dummy"]);
    expect([internetOnly(dummy), onAir(dummy), internetOnly({ ...dummy, heard_is: 2 })]).toEqual([false, true, false]);
    expect(packetChannel("dummy")).toBe("dummy");
    expect(packetLabel("dummy")).toBe("Dummy");
    expect(packetTag(packet(1, { via: "dummy" }), DUMMY)).toEqual({
      key: "radio-1",
      label: "Dummy",
      title: "Made up by the Dummy radio, which is no real radio",
      tone: "dummy",
    });
  });
});

describe("a station known from the internet alone", () => {
  it("is one with packets from the internet and none from the radio, an iGate's included", () => {
    expect([rf, gated, net, both, all, none].map(internetOnly)).toEqual([false, false, true, false, false, false]);
    expect([rf, gated, net, both, all, none].map(onAir)).toEqual([true, true, false, true, true, true]);
    expect(internetOnly({ ...net, is_me: true })).toBe(false);
  });

  it("is why the filter Heard on RF only is there: when any row has packets from the internet", () => {
    expect(anyInternet([rf, gated, none])).toBe(false);
    expect(anyInternet([rf, both])).toBe(true);
    expect(anyInternet([])).toBe(false);
    expect(anyInternet([{ ...net, own: true }])).toBe(false);
  });

  it("says on the hover card what that means; a station of the one radio alone says nothing there", () => {
    expect(heardWords(net, ONE, NOW)).toBe("Received over the internet (APRS-IS), not on the radio");
    expect(heardWords(rf, ONE, NOW)).toBeNull();
    expect(heardWords(both, ONE, NOW)).toBe("RF · Internet");
  });
});

describe("the channel of a packet of the log", () => {
  it("is RF for a packet of the radio and of ours, iGate for a third-party one and Internet for one from APRS-IS", () => {
    expect((["rf", "rf-gated", "is"] as const).map((via) => packetChannel(via))).toEqual(["rf", "gated", "is"]);
    expect((["rf", "rf-gated", "is"] as const).map((via) => packetLabel(via))).toEqual(["RF", "iGate", "Internet"]);
    expect((["rf", "rf-gated", "is"] as const).map((via) => packetTag(packet(1, { via }), ONE).label)).toEqual(["RF", "iGate", "Internet"]);
    expect(packetTag(packet(1, { via: "is", radio_id: null }), ONE).title).toBe("Received over the internet (APRS-IS), not on the radio");
  });
});

describe("a station heard on the HF radio", () => {
  const hfOnly = station("HFONLY", { heard_rf: 2, last_rf_at: ago(60), heard: heardBy([2, 2, ago(60)]) });
  const hfAndFm = station("HFFM", { heard_rf: 5, last_rf_at: ago(60), heard: heardBy([1, 3, ago(180)], [2, 2, ago(60)]) });
  const hfAndNet = station("HFNET", { heard_rf: 2, heard_is: 1, last_rf_at: ago(60), last_is_at: ago(40), heard: heardBy([2, 2, ago(60)]) });

  it("has the HF tag, with the RF one only when it was heard on the FM radio too, and every station without HF as before", () => {
    expect([hfOnly, hfAndFm, hfAndNet].map(channelsOf)).toEqual([["rf"], ["rf"], ["rf", "is"]]); // (which radio heard it is `heard`)
    expect([hfOnly, hfAndFm, hfAndNet].map((row) => labels(row))).toEqual(["HF", "RF · HF", "HF · Internet"]);
    expect([rf, gated, net, both, all].map(channelsOf)).toEqual([["rf"], ["gated"], ["is"], ["rf", "is"], ["rf", "gated", "is"]]);
  });

  it("keeps the FM tag of a station heard on both radios when HF is chosen for its messages (plan section 9: it was lost)", () => {
    const chosen = { ...hfAndFm, radio_choice: 2, radio_now: 2 };
    expect(labels(chosen)).toBe("RF · HF");
    expect(labels(chosen, TWO)).toBe("FM · HF");
  });

  it("names each radio by its short name while both are on: FM beside HF, in tags, titles, times and the packets of the log", () => {
    expect(labels(hfAndFm, TWO)).toBe("FM · HF");
    expect(labels(rf, TWO)).toBe("FM");
    expect(labels(both, TWO)).toBe("FM · Internet");
    expect(heardTags(hfAndFm, TWO, NOW).map((tag) => [tag.key, tag.label, tag.title])).toEqual([
      ["radio-1", "FM", "Heard on radio FM"],
      ["radio-2", "HF", "Heard on radio HF"],
    ]);
    expect(heardTimes(hfAndFm, TWO, NOW)).toBe("FM 3 min ago · HF 1 min ago");
    expect(heardTimes(hfAndFm, ONE, NOW)).toBe("RF 3 min ago · HF 1 min ago");
    expect(heardWords(hfAndFm, TWO, NOW)).toBe("FM 3 min ago · HF 1 min ago");
    expect(
      [
        packet(1, { via: "rf", radio_id: 1 }),
        packet(2, { via: "rf", radio_id: 2 }),
        packet(3, { via: "is", radio_id: null }),
        packet(4, { via: "rf-gated", radio_id: 1 }),
      ].map((row) => packetTag(row, TWO).label),
    ).toEqual(["FM", "HF", "Internet", "iGate"]);
    expect(packetTag(packet(1, { via: "rf", radio_id: 1 }), ONE).label).toBe("RF");
    expect(packetTag(packet(1, { via: "rf", radio_id: 1 }), TWO).title).toBe("Heard on radio FM");
  });

  it("has the HF tag in a tone of its own, the FM radio's neutral, and its own title", () => {
    expect(heardTags(hfAndFm, ONE, NOW).map((tag) => [tag.label, tag.tone])).toEqual([
      ["RF", "neutral"],
      ["HF", "hf"],
    ]);
    expect((["rf", "rf-gated", "is", "dummy"] as const).map((via) => packetTag(packet(1, { via }), ONE).tone)).toEqual(["neutral", "neutral", "info", "dummy"]);
    expect([packetTag(packet(1, { radio_id: 1 }), TWO).tone, packetTag(packet(1, { radio_id: 2 }), TWO).tone]).toEqual(["neutral", "hf"]);
    expect(titles(hfOnly, HF_ALONE)).toBe("Heard on the HF radio");
    expect(titles(hfAndFm, HF_ALONE)).toBe("Heard on radio FM; Heard on the HF radio"); // (the FM radio is off: what it heard keeps its name)
  });

  it("is told with when each radio last heard it: the RF time is the FM radio's", () => {
    expect(heardTimes(hfAndFm, ONE, NOW)).toBe("RF 3 min ago · HF 1 min ago");
    expect(heardTimes(hfOnly, HF_ALONE, NOW)).toBe("HF 1 min ago");
  });

  it("is on the air, as any station heard on a radio is, and a packet of the log says HF when it came on the HF radio", () => {
    expect([hfOnly, hfAndNet].map(onAir)).toEqual([true, true]);
    expect([hfOnly, hfAndNet].map(internetOnly)).toEqual([false, false]);
    expect(packetChannel("rf")).toBe("rf");
    expect(packetLabel("rf")).toBe("RF");
    expect(packetLabel("is")).toBe("Internet");
    expect(packetTag(packet(1, { radio_id: 2 }), HF_ALONE)).toEqual({ key: "radio-2", label: "HF", title: "Heard on the HF radio", tone: "hf" });
    expect(packetCameBy(packet(1, { radio_id: 2 }), HF_ALONE)).toBe("heard on the HF radio");
    expect(packetCameBy(packet(1, { radio_id: 2 }), TWO)).toBe("heard on radio HF");
    expect(packetCameBy(packet(1, { radio_id: 1 }), ONE)).toBe("Heard on the radio");
  });
});

describe("a station's one LoRa radio", () => {
  const LORA_ALONE = radiosOf(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), radioRow(3, "lora-tcp"));
  const heard = station("OH2LORA", { heard_rf: 2, heard: heardBy([3, 2, ago(60)]) });

  it("is RF, as the one radio of a station always was, in the sage of its kind, as its tag is once a second radio is on", () => {
    expect(heardTags(heard, LORA_ALONE, NOW).map((tag) => [tag.label, tag.tone, tag.title])).toEqual([["RF", "lora", "Heard on the radio"]]);
    expect(packetTag(packet(1, { radio_id: 3 }), LORA_ALONE)).toEqual({ key: "radio-3", label: "RF", title: "Heard on the radio", tone: "lora" });
    const withFm = radiosOf(radioRow(1, "kenwood-tnc2"), radioRow(3, "lora-tcp"));
    expect(heardTags(heard, withFm, NOW).map((tag) => [tag.label, tag.tone])).toEqual([["LoRa", "lora"]]);
    expect(packetTag(packet(1, { radio_id: 3 }), withFm).tone).toBe("lora");
  });

  it("keeps the Dummy's own dashed tone for a Dummy LoRa radio alone", () => {
    const dummy = radiosOf(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), radioRow(3, "dummy-lora"));
    expect(packetTag(packet(1, { radio_id: 3, via: "dummy" }), dummy).tone).toBe("dummy");
  });
});

describe("a station with six radios", () => {
  /** Heard on radios 1, 3, 4 and 5 at these ages, on the air. */
  const many = station("OH2SIX", {
    heard_rf: 9,
    heard_is: 1,
    last_is_at: ago(20),
    heard: {
      "1": { count: 2, last_at: ago(600) },
      "3": { count: 3, last_at: ago(60) },
      "4": { count: 1, last_at: ago(30) },
      "5": { count: 3, last_at: ago(3600) },
    },
  });

  it("shows the two radios that heard it last by their names, in the order of their boxes, then +n for the rest and Internet apart", () => {
    const tags = heardTags(many, SIX, NOW);
    expect(tags.map((tag) => [tag.key, tag.label, tag.tone])).toEqual([
      ["radio-3", "Shack", "neutral"],
      ["radio-4", "20 m", "dummy"],
      ["more", "+2", "neutral"],
      ["is", "Internet", "info"],
    ]);
    expect(tags[0]?.title).toBe("Heard on radio Shack");
  });

  it("lists in the title of +n the rest with their times, in the order of their boxes", () => {
    expect(heardTags(many, SIX, NOW).find((tag) => tag.key === "more")?.title).toBe("FM: 10 min ago; FM 3: 1 h ago");
  });

  it("has no +n while the radios fit, and the room is a number of tags", () => {
    expect(heardTags(many, SIX, NOW, 4).map((tag) => tag.label)).toEqual(["FM", "Shack", "20 m", "FM 3", "Internet"]);
    const two = { ...many, heard: { "1": { count: 2, last_at: ago(600) }, "2": { count: 1, last_at: ago(30) } } };
    expect(heardTags(two, SIX, NOW).map((tag) => tag.label)).toEqual(["FM", "HF", "Internet"]);
  });

  it("lists every radio with its time on the card and the hover card, with a colon beside a typed name or a number", () => {
    expect(heardTimes(many, SIX, NOW)).toBe("FM: 10 min ago · Shack: 1 min ago · 20 m: 30 s ago · FM 3: 1 h ago · Internet: 20 s ago");
    expect(heardWords(many, SIX, NOW)).toBe(heardTimes(many, SIX, NOW));
  });

  it("gives no radio to a station heard on the air only as an iGate's packets: the iGate says it", () => {
    const viaGate = station("OH2GATE", { heard_rf: 0, heard_rf_gated: 2, last_rf_gated_at: ago(60), heard: { "3": { count: 2, last_at: ago(60) } } });
    expect(heardTags(viaGate, SIX, NOW).map((tag) => tag.label)).toEqual(["iGate"]);
  });

  it("orders the parts by the boxes and puts a radio the page does not know last", () => {
    const odd = { ...many, heard: { "9": { count: 1, last_at: ago(10) }, "1": { count: 1, last_at: ago(20) } } };
    expect(heardParts(odd, SIX).map((part) => part.key)).toEqual(["radio-1", "radio-9", "is"]);
  });

  it("names a packet's radio and says which radio heard an iGate's packet", () => {
    expect(packetTag(packet(1, { radio_id: 4, via: "dummy" }), SIX)).toEqual({
      key: "radio-4",
      label: "20 m",
      title: "Heard on radio 20 m",
      tone: "dummy",
    });
    expect(packetTag(packet(2, { radio_id: 3, via: "rf-gated" }), SIX).title).toBe(
      "Heard on the radio from an iGate, which took it from the internet; Heard on radio Shack",
    );
    expect(packetTag(packet(2, { radio_id: 3, via: "rf-gated" }), ONE).title).toBe("Heard on the radio from an iGate, which took it from the internet");
    expect(packetCameBy(packet(1, { radio_id: 3 }), SIX)).toBe("heard on radio Shack");
  });
});

describe("a radio that is off or removed", () => {
  const removed = radioRow(3, "kiss", { name: "Shack", number: 2, removed: true, enabled: false, state: "stopped" });
  const ONE_AND_REMOVED = radiosOf(FM, HF_OFF, removed);
  const heardOnBoth = station("OH2OLD", { heard_rf: 5, heard: { "1": { count: 2, last_at: ago(60) }, "3": { count: 3, last_at: ago(120) } } });

  it("keeps its name on what came by it, dimmed once it is removed, beside the one radio's word", () => {
    expect(heardTags(heardOnBoth, ONE_AND_REMOVED, NOW).map((tag) => [tag.label, tag.tone, tag.title])).toEqual([
      ["RF", "neutral", "Heard on the radio"],
      ["Shack", "removed", "Heard on radio Shack"],
    ]);
    expect(packetTag(packet(1, { radio_id: 3 }), ONE_AND_REMOVED)).toEqual({
      key: "radio-3",
      label: "Shack",
      title: "Heard on radio Shack",
      tone: "removed",
    });
  });

  it("is named while it is off: an HF radio switched off keeps its word HF, and its title names it (plan section 6: a row that came by a radio that is now off always carries its name)", () => {
    expect(heardTags(station("OH2HFOFF", { heard_rf: 2, heard: heardBy([2, 2]) }), ONE, NOW).map((tag) => [tag.label, tag.tone])).toEqual([["HF", "hf"]]);
    const hfAndFm = station("HFFM", { heard_rf: 5, last_rf_at: ago(60), heard: heardBy([1, 3, ago(180)], [2, 2, ago(60)]) });
    expect(titles(hfAndFm, ONE)).toBe("Heard on the radio; Heard on radio HF");
  });
});

describe("the tone of a radio's tag", () => {
  it("follows the kind, dashed for a Dummy whatever its kind, dimmed once removed", () => {
    const tone = (extra: Partial<RadioRow>, type = "kenwood-tnc2") => radioTone(radiosOf(radioRow(1, type, extra))[0]);
    expect([
      tone({}),
      tone({}, "mercury"),
      tone({ kind: "lora" }),
      tone({}, "dummy"),
      tone({}, "dummy-hf"),
      tone({ removed: true }, "mercury"),
      tone({ removed: true }, "dummy"),
    ]).toEqual(["neutral", "hf", "lora", "dummy", "dummy", "removed", "removed"]);
  });
});
