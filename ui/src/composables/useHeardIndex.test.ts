import { describe, expect, it } from "vitest";
import { shallowReactive, shallowRef } from "vue";
import { useHeardIndex } from "@/composables/useHeardIndex";
import type { StationRow } from "@/protocol/protocol";
import { configValues, station } from "@/test/fixtures";

function rows(...list: StationRow[]) {
  return shallowReactive(new Map(list.map((row) => [row.call, row])));
}

describe("useHeardIndex", () => {
  it("draws our own station with the symbol of the settings when the daemon heard none", () => {
    const heard = rows(station("OH2GBA", { is_me: true, symbol_table: "", symbol_code: "" }), station("OH2PU-9"));
    const { stations } = useHeardIndex(heard, shallowRef(configValues({ "station/symbol_table": "/", "station/symbol_code": "-" })));
    expect([stations.value.get("OH2GBA")?.symbol_table, stations.value.get("OH2GBA")?.symbol_code]).toEqual(["/", "-"]);
    expect(stations.value.get("OH2PU-9")?.symbol_code).toBe(">");
  });

  it("has the path the daemon suggests for each station, and the stations that were heard direct", () => {
    const heard = rows(station("OH2PU-9", { suggested_path: "OH2RCH-2", heard_direct: 2 }), station("OH2RDG", { suggested_path: null }));
    const { suggestions, heardDirect } = useHeardIndex(heard, shallowRef(null));
    expect([...suggestions.value]).toEqual([
      ["OH2PU-9", "OH2RCH-2"],
      ["OH2RDG", null],
    ]);
    expect([...heardDirect.value]).toEqual(["OH2PU-9"]);
  });

  it("follows the stations as they come", () => {
    const heard = rows();
    const { heardDirect } = useHeardIndex(heard, shallowRef(null));
    expect(heardDirect.value.size).toBe(0);
    heard.set("OH2RDG", station("OH2RDG", { heard_direct: 1 }));
    expect([...heardDirect.value]).toEqual(["OH2RDG"]);
  });
});
