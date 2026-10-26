import type { LayerSpecification, StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";
import { ATTRIBUTION, DARK, FONT_MEDIUM, FONT_REGULAR, LIGHT, basemapStyle } from "@/lib/basemapstyle";

const GLYPHS = "http://host/fonts/{fontstack}/{range}.pbf";
const ARCHIVE = "http://host/basemap.pmtiles";
const WORLD = "http://host/basemap-world.pmtiles";
const DETAIL_ONLY = { detail: ARCHIVE, world: null };
const NONE = { detail: null, world: null };

function layers(style: StyleSpecification): LayerSpecification[] {
  return style.layers;
}

describe("basemapStyle", () => {
  it("is a blank background without the archive, and has no source", () => {
    const style = basemapStyle(NONE, false, GLYPHS);
    expect(layers(style).map((l) => l.id)).toEqual(["background"]);
    expect(Object.keys(style.sources)).toEqual([]);
  });

  it("reads the archive through the pmtiles protocol, the zooms being those of its header, and credits OpenStreetMap", () => {
    const style = basemapStyle(DETAIL_ONLY, false, GLYPHS);
    expect(style.sources.base).toMatchObject({ type: "vector", url: `pmtiles://${ARCHIVE}`, attribution: ATTRIBUTION });
    expect(style.sources.base).not.toHaveProperty("maxzoom");
    expect(ATTRIBUTION).toContain("OpenStreetMap");
    expect(style.glyphs).toBe(GLYPHS);
  });

  it("has the layers the map is to draw", () => {
    const ids = layers(basemapStyle(DETAIL_ONLY, false, GLYPHS)).map((l) => l.id);
    for (const wanted of [
      "earth",
      "landuse-forest",
      "landuse-residential",
      "landuse-industrial",
      "landuse-park",
      "water",
      "road-highway",
      "road-major",
      "road-minor",
      "road-path",
      "buildings",
      "boundary-country",
      "road-names",
      "place-city",
      "place-town",
      "place-village",
    ]) {
      expect(ids).toContain(wanted);
    }
  });

  it("has unique layer ids, every one on a source the style has", () => {
    for (const dark of [false, true]) {
      const style = basemapStyle(DETAIL_ONLY, dark, GLYPHS);
      const ids = layers(style).map((l) => l.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const layer of layers(style)) if ("source" in layer) expect(Object.keys(style.sources)).toContain(layer.source);
    }
  });

  it("draws the buildings at zoom 14 and not before", () => {
    const buildings = layers(basemapStyle(DETAIL_ONLY, false, GLYPHS)).find((l) => l.id === "buildings");
    expect(buildings?.minzoom).toBe(14);
  });

  it("draws the roads wider with their class: highway over major over minor over path", () => {
    const style = basemapStyle(DETAIL_ONLY, false, GLYPHS);
    const width = (id: string): number => {
      const paint = layers(style).find((l) => l.id === id)?.paint as { "line-width": unknown[] } | undefined;
      const expression = paint?.["line-width"] ?? [];
      return Number(expression[expression.indexOf(14) + 1]); // the width at zoom 14
    };
    expect(width("road-highway")).toBeGreaterThan(width("road-major"));
    expect(width("road-major")).toBeGreaterThan(width("road-minor"));
    expect(width("road-minor")).toBeGreaterThan(width("road-path"));
  });

  it("writes the labels in the two fonts the page ships, with the Finnish name first", () => {
    const style = basemapStyle(DETAIL_ONLY, false, GLYPHS);
    const fonts = new Set(layers(style).flatMap((l) => (l.type === "symbol" ? (l.layout?.["text-font"] ?? []) : [])));
    expect([...fonts].sort()).toEqual([FONT_MEDIUM, FONT_REGULAR].sort());
    const city = layers(style).find((l) => l.id === "place-city");
    expect(JSON.stringify(city?.type === "symbol" ? city.layout?.["text-field"] : null)).toContain("name:fi");
  });

  it("is drawn from the world map alone with its borders, coastlines (water) and the names of countries from zoom 1 and of big cities from zoom 3", () => {
    const style = basemapStyle({ detail: null, world: WORLD }, false, GLYPHS);
    const world = layers(style);
    const by = (id: string) => world.find((l) => l.id === `world-${id}`);
    expect(by("water")).toBeDefined();
    expect(by("boundary-country")).toBeDefined();
    expect(by("place-country")).toMatchObject({ minzoom: 1, filter: ["==", ["get", "kind"], "country"] });
    expect(by("place-city")).toMatchObject({ minzoom: 3 });
    expect(Object.keys(style.sources)).toEqual(["world"]);
  });

  it("is dark in the dark scheme: a darker sea, land and text of another colour", () => {
    const light = basemapStyle(DETAIL_ONLY, false, GLYPHS);
    const dark = basemapStyle(DETAIL_ONLY, true, GLYPHS);
    const sea = (s: StyleSpecification): unknown => (layers(s)[0] as { paint: Record<string, unknown> }).paint["background-color"];
    expect(sea(light)).toBe(LIGHT.sea);
    expect(sea(dark)).toBe(DARK.sea);
    expect(LIGHT.text).not.toBe(DARK.text);
    expect(JSON.stringify(dark)).not.toContain(LIGHT.land);
  });

  describe("with the world map under the detailed one", () => {
    const both = { detail: ARCHIVE, world: WORLD };
    const ids = (style: StyleSpecification): string[] => layers(style).map((l) => l.id);

    it("has a source for each file, the layers of each on its own source", () => {
      const style = basemapStyle(both, false, GLYPHS);
      expect(style.sources.base).toMatchObject({ url: `pmtiles://${ARCHIVE}` });
      expect(style.sources.world).toMatchObject({ type: "vector", url: `pmtiles://${WORLD}` });
      for (const layer of layers(style)) if ("source" in layer) expect(layer.source).toBe(layer.id.startsWith("world-") ? "world" : "base");
    });

    it("draws the world's layers first and the detailed map's on top of them, the same layers in the same order", () => {
      const all = ids(basemapStyle(both, false, GLYPHS));
      const detail = ids(basemapStyle(DETAIL_ONLY, false, GLYPHS));
      const world = detail.filter((id) => id !== "background").map((id) => `world-${id}`);
      expect(all).toEqual(["background", ...world, ...detail.filter((id) => id !== "background")]);
      expect(new Set(all).size).toBe(all.length);
    });

    it("is the world alone while the detailed map is not there, and a blank background with neither", () => {
      const world = basemapStyle({ detail: null, world: WORLD }, false, GLYPHS);
      expect(Object.keys(world.sources)).toEqual(["world"]);
      expect(ids(world).every((id) => id === "background" || id.startsWith("world-"))).toBe(true);
      expect(layers(world)[0]).toMatchObject({ paint: { "background-color": LIGHT.sea } });
      expect(ids(basemapStyle(NONE, false, GLYPHS))).toEqual(["background"]);
    });

    it("keeps the paint of a layer when it is drawn from the world's file", () => {
      const style = basemapStyle(both, true, GLYPHS);
      const byId = new Map(layers(style).map((l) => [l.id, l] as const));
      expect(byId.get("world-water")).toMatchObject({ "source-layer": "water", paint: byId.get("water")?.paint });
    });
  });
});
