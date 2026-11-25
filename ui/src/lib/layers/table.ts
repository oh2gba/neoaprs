// The map's layers as the Layers box lists them (components/MapLayers.vue), one table: each row's
// id
// (the key its tick is kept by in this browser), its name in the catalogue, its mark
// (lib/layers/marks.ts), its part (what the station and the page draw themselves, then, under a
// thin
// line, what comes from a receiver or the internet) and whether it is ticked out of the box. Rows
// of things are listed only while the station has a source for them (the topic `map`'s `layers`),
// with the source's own name where it is a service.
import type { MessageId } from "@/i18n/catalogue";
import type { MarkName } from "@/lib/layers/marks";
import { LAYER_NAMES, SOURCE_NAMES, isService, type LayerName } from "@/lib/layers/sources";
import type { MapLayer } from "@/protocol/protocol";

/** A row of the box. */
export type LayerId = "tracks" | "aloha" | "grid" | "daynight" | LayerName;

export interface LayerEntry {
  readonly id: LayerId;
  readonly name: MessageId;
  readonly mark: MarkName;
  readonly part: "own" | "outside";
  /** Ticked out of the box. */
  readonly tick: boolean;
}

export const LAYER_TABLE: readonly LayerEntry[] = [
  { id: "tracks", name: "layers.box.tracks", mark: "track", part: "own", tick: true },
  { id: "aloha", name: "layers.box.aloha", mark: "circle", part: "own", tick: true },
  { id: "grid", name: "layers.box.grid", mark: "grid", part: "own", tick: false },
  { id: "daynight", name: "layers.box.daynight", mark: "daynight", part: "own", tick: false },
  { id: "aircraft", name: LAYER_NAMES.aircraft, mark: "airliner", part: "outside", tick: false },
  { id: "ships", name: LAYER_NAMES.ships, mark: "hull", part: "outside", tick: false },
];

/** A row as the box draws it now: the source's own name after the layer's where the source is a
 * service, else null. */
export interface LayerRow extends LayerEntry {
  readonly source: string | null;
}

/** The rows to draw: the station's own always, a layer of things only while its source (in force) is
 * not "none". */
export function layerRows(layers: readonly MapLayer[] | undefined): LayerRow[] {
  const sourceOf = (id: LayerId) => layers?.find((one) => one.layer === id)?.source ?? "none";
  return LAYER_TABLE.flatMap((entry): LayerRow[] => {
    if (entry.part === "own") return [{ ...entry, source: null }];
    const source = sourceOf(entry.id);
    if (source === "none") return [];
    return [{ ...entry, source: isService(source) ? SOURCE_NAMES[source] : null }];
  });
}
