import { describe, expect, it } from "vitest";
import { pairField, pairFieldOf } from "@/lib/settingspair";
import type { Choice } from "@/lib/settingchoices";

const choicesOf = (key: string, values: Record<string, string>) =>
  (pairField(key, values)?.choices ?? []).map((c) => (c as Choice).value);

describe("pairFieldOf", () => {
  it("takes a pair's key apart into its two radios and its field", () => {
    expect([pairFieldOf("pair/1/2/enabled"), pairFieldOf("pair/3/12/ssid")]).toEqual([
      { low: 1, high: 2, field: "enabled" },
      { low: 3, high: 12, field: "ssid" },
    ]);
  });

  it("is null for a key that is no pair's: radios out of order or the same, a field it has not, a radio's own key", () => {
    for (const key of [
      "pair/2/1/enabled",
      "pair/2/2/ssid",
      "pair/0/2/ssid",
      "pair/1/2/call",
      "pair/1/2",
      "radio/1/digipeat",
      "station/call",
    ])
      expect(pairFieldOf(key), key).toBeNull();
  });
});

describe("pairField", () => {
  it("makes the Enable a tickbox with the pair's (i)", () => {
    expect(pairField("pair/1/2/enabled", {})).toEqual({
      label: "Enable",
      name: "Pair of radios",
      kind: "bool",
      tipLabel: "About passing between two radios",
      tip: [
        "A packet heard on one of the two radios goes out once on the other when its path names this call. Give the call to stations that want to cross.",
        "A WIDE path alone never goes across.",
      ],
    });
  });

  it("makes the Call a choice of the calls on the station's base call, 15 down to 1", () => {
    const field = pairField("pair/1/2/ssid", {
      "station/call": "oh2gba",
      "pair/1/2/enabled": "true",
      "pair/1/2/ssid": "15",
    });
    expect([field?.label, field?.kind]).toEqual(["Call", "choice"]);
    expect(field?.choices?.[0]).toEqual({ value: "15", label: "OH2GBA-15" });
    expect(choicesOf("pair/1/2/ssid", { "station/call": "OH2GBA" })).toEqual([
      "15",
      "14",
      "13",
      "12",
      "11",
      "10",
      "9",
      "8",
      "7",
      "6",
      "5",
      "4",
      "3",
      "2",
      "1",
    ]);
  });

  it("leaves out the station's own SSID and those of the other pairs that are on, never its own", () => {
    const values = {
      "station/call": "OH2GBA-9",
      "pair/1/2/enabled": "true",
      "pair/1/2/ssid": "15",
      "pair/1/3/enabled": "true",
      "pair/1/3/ssid": "14",
      "pair/2/3/enabled": "false",
      "pair/2/3/ssid": "13",
    };
    expect(choicesOf("pair/1/2/ssid", values)).toEqual([
      "15",
      "13",
      "12",
      "11",
      "10",
      "8",
      "7",
      "6",
      "5",
      "4",
      "3",
      "2",
      "1",
    ]);
    expect(choicesOf("pair/2/3/ssid", values)).toEqual([
      "13",
      "12",
      "11",
      "10",
      "8",
      "7",
      "6",
      "5",
      "4",
      "3",
      "2",
      "1",
    ]);
  });

  it("keeps its own value among the choices even where the station's call has it", () => {
    expect(
      choicesOf("pair/1/2/ssid", { "station/call": "OH2GBA-12", "pair/1/2/enabled": "true", "pair/1/2/ssid": "12" }),
    ).toContain("12");
  });

  it("names the calls by the SSID alone while the station has no call", () => {
    expect(pairField("pair/1/2/ssid", { "station/call": "" })?.choices?.[3]).toEqual({ value: "12", label: "-12" });
  });

  it("says nothing of a key that is no pair's", () => {
    expect(pairField("radio/1/digipeat", {})).toBeUndefined();
  });
});
