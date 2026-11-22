import { afterEach, describe, expect, it, vi } from "vitest";
import type { Map as MapLibreMap } from "maplibre-gl";
import { NO_DAYNIGHT } from "@/lib/layers/daynight";
import { addDayNightLayers, setDayNightData } from "@/lib/layers/daynightlayers";

interface Added {
  layer: { id: string; type: string; maxzoom: number; filter: unknown; paint: Record<string, unknown> };
  before: string | undefined;
}

function fakeMap(styleLayers: { id: string; type: string }[]) {
  const sources = new Map<string, unknown>();
  const added: Added[] = [];
  const setData = vi.fn();
  const map = {
    getSource: (id: string) => (sources.has(id) ? { setData } : undefined),
    addSource: (id: string, source: unknown) => void sources.set(id, source),
    addLayer: (layer: Added["layer"], before?: string) => void added.push({ layer, before }),
    getStyle: () => ({ layers: styleLayers }),
  };
  return { map: map as unknown as MapLibreMap, added, sources, setData };
}

afterEach(() => {
  document.documentElement.removeAttribute("style");
});

describe("the Day and night layers", () => {
  it("are two fill layers, the twilight and over it the night, filtered by depth", () => {
    const { map, added, sources } = fakeMap([]);
    addDayNightLayers(map, NO_DAYNIGHT);
    expect(sources.get("daynight")).toEqual({ type: "geojson", data: NO_DAYNIGHT });
    expect(added.map((one) => [one.layer.id, one.layer.type, one.layer.filter])).toEqual([
      ["daynight-twilight", "fill", ["==", ["get", "depth"], "twilight"]],
      ["daynight-night", "fill", ["==", ["get", "depth"], "night"]],
    ]);
  });

  it("fade out between zoom 5 and 6 and are not drawn from zoom 6", () => {
    const { map, added } = fakeMap([]);
    addDayNightLayers(map, NO_DAYNIGHT);
    for (const { layer } of added) {
      expect(layer.maxzoom).toBe(6);
      expect(layer.paint["fill-opacity"]).toEqual(["interpolate", ["linear"], ["zoom"], 5, 1, 6, 0]);
    }
  });

  it("lie before the first layer of names of the base map, and on top when it has none", () => {
    const names = fakeMap([
      { id: "land", type: "fill" },
      { id: "roads", type: "line" },
      { id: "places", type: "symbol" },
      { id: "water-names", type: "symbol" },
    ]);
    addDayNightLayers(names.map, NO_DAYNIGHT);
    expect(names.added.map((one) => one.before)).toEqual(["places", "places"]);
    const bare = fakeMap([{ id: "land", type: "fill" }]);
    addDayNightLayers(bare.map, NO_DAYNIGHT);
    expect(bare.added.map((one) => one.before)).toEqual([undefined, undefined]);
  });

  it("are made once for a style", () => {
    const { map, added } = fakeMap([]);
    addDayNightLayers(map, NO_DAYNIGHT);
    addDayNightLayers(map, NO_DAYNIGHT);
    expect(added).toHaveLength(2);
  });

  it("take their colours from the palette, else the light theme's washes", () => {
    const plain = fakeMap([]);
    addDayNightLayers(plain.map, NO_DAYNIGHT);
    expect(plain.added.map((one) => one.layer.paint["fill-color"])).toEqual([
      "rgba(11, 26, 58, 0.1)",
      "rgba(11, 26, 58, 0.14)",
    ]);
    document.documentElement.style.setProperty("--map-twilight", "rgba(0, 0, 0, 0.25)");
    document.documentElement.style.setProperty("--map-night", "rgba(0, 0, 0, 0.4)");
    const dark = fakeMap([]);
    addDayNightLayers(dark.map, NO_DAYNIGHT);
    expect(dark.added.map((one) => one.layer.paint["fill-color"])).toEqual([
      "rgba(0, 0, 0, 0.25)",
      "rgba(0, 0, 0, 0.4)",
    ]);
  });

  it("have their data set on the one source", () => {
    const { map, setData } = fakeMap([]);
    addDayNightLayers(map, NO_DAYNIGHT);
    setDayNightData(map, NO_DAYNIGHT);
    expect(setData).toHaveBeenCalledWith(NO_DAYNIGHT);
  });
});
