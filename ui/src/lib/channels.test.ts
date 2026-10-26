import { describe, expect, it } from "vitest";
import {
  anyInternet,
  channelLabel,
  channelsOf,
  channelTitle,
  heardByChannel,
  internetOnly,
  onAir,
  packetChannel,
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
    expect([rf, gated, net, both, all, none].map(channelLabel)).toEqual(["RF", "iGate", "Internet", "RF · Internet", "RF · iGate · Internet", ""]);
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
    expect((["rf", "rf-gated", "is"] as const).map(packetChannel)).toEqual(["rf", "gated", "is"]);
    expect((["rf", "rf-gated", "is"] as const).map(packetLabel)).toEqual(["RF", "iGate", "Internet"]);
    expect(packetTitle("is")).toBe("Received over the internet (APRS-IS), not on the radio");
  });
});
