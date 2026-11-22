// The layers of the Day and night shade (lib/layers/daynight.ts): the twilight and over it the
// night, two washes whose colours carry their own strength (styles/tokens.css), faded out between
// zoom 5 and 6 and not drawn beyond. They lie over every fill of the base map (the world map's and
// the detailed one's) and under its names, so that a name is read as well on the night side. The colours are read when the layers are made, which happens again
// whenever the style is set.
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { paletteColor } from "@/lib/alohalayers";
import type { DayNightCollection } from "@/lib/layers/daynight";

const DAYNIGHT_SOURCE = "daynight";
const FADE_FROM = 5;
const FADE_TO = 6;

/** The first layer of names above the last layer that is not names, if there is one. */
function firstNamesAbove(map: MapLibreMap): string | undefined {
  const layers = map.getStyle().layers;
  let last = -1;
  layers.forEach((layer, at) => {
    if (layer.type !== "symbol") last = at;
  });
  return layers[last + 1]?.id;
}

export function addDayNightLayers(map: MapLibreMap, data: DayNightCollection): void {
  if (map.getSource(DAYNIGHT_SOURCE)) return;
  map.addSource(DAYNIGHT_SOURCE, { type: "geojson", data });
  const names = firstNamesAbove(map);
  const shades = [
    { depth: "twilight", token: "--map-twilight", fallback: "rgba(11, 26, 58, 0.1)" },
    { depth: "night", token: "--map-night", fallback: "rgba(11, 26, 58, 0.14)" },
  ] as const;
  for (const { depth, token, fallback } of shades) {
    map.addLayer(
      {
        id: `daynight-${depth}`,
        type: "fill",
        source: DAYNIGHT_SOURCE,
        maxzoom: FADE_TO,
        filter: ["==", ["get", "depth"], depth],
        paint: {
          "fill-antialias": false,
          "fill-color": paletteColor(token, fallback),
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], FADE_FROM, 1, FADE_TO, 0],
        },
      },
      names,
    );
  }
}

export function setDayNightData(map: MapLibreMap, data: DayNightCollection): void {
  void map.getSource<GeoJSONSource>(DAYNIGHT_SOURCE)?.setData(data);
}
