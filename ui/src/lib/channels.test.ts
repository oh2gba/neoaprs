import { describe, expect, it } from "vitest";
import {
  anyInternet,
  channelLabel,
  channelsOf,
  channelTags,
  channelTitle,
  heardByChannel,
  internetOnly,
  onAir,
  packetChannel,
  packetTone,
  packetLabel,
  packetTitle,
} from "@/lib/channels";
import { NOW, ago, station } from "@/test/fixtures";

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
  });

  it("make the small label of a row: one word, or two or three joined with a middle dot", () => {
    expect([rf, gated, net, both, all, none].map((row) => channelLabel(row))).toEqual([
      "RF",
      "iGate",
      "Internet",
      "RF · Internet",
      "RF · iGate · Internet",
      "",
    ]);
  });

  it("have a title that says what each word means", () => {
    expect(channelTitle(rf)).toBe("Heard on the radio");
    expect(channelTitle(gated)).toBe("Heard on the radio from an iGate, which took it from the internet");
    expect(channelTitle(net)).toBe("Received over the internet (APRS-IS), not on the radio");
    expect(channelTitle(both)).toBe("Heard on the radio; Received over the internet (APRS-IS), not on the radio");
    expect(channelTitle(none)).toBe("");
  });

  it("are told with when each was last heard: RF 3 min ago · Internet 40 s ago", () => {
    expect(heardByChannel(both, NOW)).toBe("RF 3 min ago · Internet 40 s ago");
    expect(heardByChannel(rf, NOW)).toBe("RF 1 min ago");
    expect(heardByChannel(all, NOW)).toBe("RF 1 min ago · iGate 2 min ago · Internet 30 s ago");
    expect(heardByChannel(none, NOW)).toBe("");
  });
});

describe("a station of the Dummy radio", () => {
  const dummy = station("QDUMMY-1", { heard_rf: 0, heard_dummy: 3, last_rf_at: null, last_dummy_at: ago(90) });

  it("is labelled Dummy, joined to the others, told by its own time, and is on the air for everything but the internet", () => {
    expect(channelsOf(dummy)).toEqual(["dummy"]);
    expect(channelLabel(dummy)).toBe("Dummy");
    expect(channelLabel({ ...dummy, heard_rf: 1 })).toBe("RF · Dummy");
    expect(channelTitle(dummy)).toBe("Made up by the Dummy radio, which is no real radio");
    expect(heardByChannel(dummy, NOW)).toBe("Dummy 1 min ago");
    expect([internetOnly(dummy), onAir(dummy), internetOnly({ ...dummy, heard_is: 2 })]).toEqual([false, true, false]);
    expect(packetChannel("dummy")).toBe("dummy");
    expect(packetLabel("dummy")).toBe("Dummy");
    expect(packetTitle("dummy")).toBe("Made up by the Dummy radio, which is no real radio");
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
});

describe("the channel of a packet of the log", () => {
  it("is RF for a packet of the radio and of ours, iGate for a third-party one and Internet for one from APRS-IS", () => {
    expect((["rf", "rf-gated", "is"] as const).map((via) => packetChannel(via))).toEqual(["rf", "gated", "is"]);
    expect((["rf", "rf-gated", "is"] as const).map((via) => packetLabel(via))).toEqual(["RF", "iGate", "Internet"]);
    expect(packetTitle("is")).toBe("Received over the internet (APRS-IS), not on the radio");
  });
});

describe("a station heard on the HF radio", () => {
  const hfOnly = station("HFONLY", { heard_rf: 2, heard_fm: 0, heard_hf: 2, last_rf_at: ago(60), last_fm_at: null, last_hf_at: ago(60) });
  const hfAndFm = station("HFFM", { heard_rf: 5, heard_fm: 3, heard_hf: 2, last_rf_at: ago(60), last_fm_at: ago(180), last_hf_at: ago(60) });
  const hfAndNet = station("HFNET", { heard_rf: 2, heard_fm: 0, heard_hf: 2, heard_is: 1, last_hf_at: ago(60), last_is_at: ago(40) });

  it("has the HF tag, with the RF one only when it was heard on the FM radio too, and every station without HF as before", () => {
    expect([hfOnly, hfAndFm, hfAndNet].map(channelsOf)).toEqual([["hf"], ["rf", "hf"], ["hf", "is"]]);
    expect([hfOnly, hfAndFm, hfAndNet].map((row) => channelLabel(row))).toEqual(["HF", "RF · HF", "HF · Internet"]);
    expect([rf, gated, net, both, all].map(channelsOf)).toEqual([["rf"], ["gated"], ["is"], ["rf", "is"], ["rf", "gated", "is"]]);
  });

  it("names the FM radio FM beside HF while the HF radio is on, and RF as it always was otherwise: tags, titles, times and the packets of the log", () => {
    expect(channelLabel(hfAndFm, true)).toBe("FM · HF");
    expect(channelLabel(rf, true)).toBe("FM");
    expect(channelLabel(rf)).toBe("RF");
    expect(channelLabel(both, true)).toBe("FM · Internet");
    expect(channelTags(hfAndFm, true).map((tag) => [tag.channel, tag.label, tag.title])).toEqual([
      ["rf", "FM", "Heard on the FM radio"],
      ["hf", "HF", "Heard on the HF radio"],
    ]);
    expect(channelTitle(hfAndFm, true)).toBe("Heard on the FM radio; Heard on the HF radio");
    expect(heardByChannel(hfAndFm, NOW, true)).toBe("FM 3 min ago · HF 1 min ago");
    expect(heardByChannel(hfAndFm, NOW)).toBe("RF 3 min ago · HF 1 min ago");
    expect([
      packetLabel("rf", "fm", true),
      packetLabel("rf", "hf", true),
      packetLabel("rf", "fm"),
      packetLabel("is", "", true),
      packetLabel("rf-gated", "fm", true),
    ]).toEqual(["FM", "HF", "RF", "Internet", "iGate"]);
    expect(packetTitle("rf", "fm", true)).toBe("Heard on the FM radio");
  });

  it("has the HF tag in a tone of its own, the FM radio's neutral, and its own title", () => {
    expect(channelTags(hfAndFm).map((tag) => [tag.channel, tag.label, tag.tone])).toEqual([
      ["rf", "RF", "neutral"],
      ["hf", "HF", "hf"],
    ]);
    expect((["rf", "rf-gated", "is", "dummy"] as const).map((via) => packetTone(via))).toEqual(["neutral", "neutral", "info", "dummy"]);
    expect([packetTone("rf", "fm"), packetTone("rf", "hf")]).toEqual(["neutral", "hf"]);
    expect(channelTitle(hfOnly)).toBe("Heard on the HF radio");
    expect(channelTitle(hfAndFm)).toBe("Heard on the radio; Heard on the HF radio");
  });

  it("is told with when each radio last heard it: the RF time is the FM radio's", () => {
    expect(heardByChannel(hfAndFm, NOW)).toBe("RF 3 min ago · HF 1 min ago");
    expect(heardByChannel(hfOnly, NOW)).toBe("HF 1 min ago");
  });

  it("is on the air, as any station heard on a radio is, and a packet of the log says HF when it came on the HF radio", () => {
    expect([hfOnly, hfAndNet].map(onAir)).toEqual([true, true]);
    expect([hfOnly, hfAndNet].map(internetOnly)).toEqual([false, false]);
    expect(packetChannel("rf", "hf")).toBe("hf");
    expect(packetLabel("rf", "hf")).toBe("HF");
    expect(packetLabel("rf", "fm")).toBe("RF");
    expect(packetLabel("rf")).toBe("RF");
    expect(packetLabel("is", "")).toBe("Internet");
    expect(packetTitle("rf", "hf")).toBe("Heard on the HF radio");
  });
});
