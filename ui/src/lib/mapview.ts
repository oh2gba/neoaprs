// Where the map looks, as it is remembered between visits.
import type { Marker } from "maplibre-gl";
import type { MarkerDom } from "@/lib/markerdom";
import { readStored, writeStored } from "@/lib/storage";
import { MAX_ZOOM } from "@/lib/basemapstyle";

interface MapView {
  lat: number;
  lon: number;
  zoom: number;
}

/** A request to fly to a station; `n` counts up, so that asking for the same station again flies there again. */
/** A marker on the map: the MapLibre marker, its DOM and where it stands. */
export interface Placed {
  marker: Marker;
  dom: MarkerDom;
  lat: number;
  lon: number;
}

export interface Focus {
  call: string;
  n: number;
}

/** Where we are (the station's position of the settings). */
export interface Home {
  lat: number;
  lon: number;
}

const KEY = "mapview";

function isView(value: unknown): value is MapView {
  if (typeof value !== "object" || value === null) return false;
  const { lat, lon, zoom } = value as Record<string, unknown>;
  return (
    typeof lat === "number" &&
    typeof lon === "number" &&
    typeof zoom === "number" &&
    Math.abs(lat) <= 90 &&
    Math.abs(lon) <= 180 &&
    zoom >= 0 &&
    zoom <= MAX_ZOOM
  );
}

/** The view of the last visit, null when none was kept (or it is garbage). */
export function readView(): MapView | null {
  const text = readStored(KEY);
  if (text === null) return null;
  try {
    const value: unknown = JSON.parse(text);
    return isView(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeView(view: MapView): void {
  writeStored(KEY, JSON.stringify({ lat: +view.lat.toFixed(5), lon: +view.lon.toFixed(5), zoom: +view.zoom.toFixed(2) }));
}
