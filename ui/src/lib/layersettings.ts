// Settings, Map: the rows Aircraft and Ships and the receiver's address each may have (components/SettingsLayer.vue). The four keys and what each says of itself; the sources a station is offered are the daemon's (`map.layers[i].offered`), and a stored
// source that is not among them shows as None. The address field is there only while the row's choice is My own receiver.
import type { Choice } from "@/lib/settingchoices";
import type { FieldSpec } from "@/lib/settings";
import { SOURCE_NAMES, isService, type LayerName, type SourceName } from "@/lib/layers/sources";
import { t } from "@/i18n";
import { AIRCRAFT_SOURCES, SHIP_SOURCES } from "@/protocol/lists";
import type { MapLayer } from "@/protocol/protocol";

/** The four keys: which layer each is of, and whether it chooses the source or holds the address of an own receiver. */
const KEYS: Readonly<Record<string, { layer: LayerName; role: "source" | "address" }>> = {
  "map/aircraft": { layer: "aircraft", role: "source" },
  "map/aircraft_host": { layer: "aircraft", role: "address" },
  "map/ships": { layer: "ships", role: "source" },
  "map/ships_host": { layer: "ships", role: "address" },
};

/** The layer a key belongs to and its role, or null for any other key. */
export const layerKey = (key: string): { layer: LayerName; role: "source" | "address" } | null => KEYS[key] ?? null;

/** The key that chooses the source of a layer. */
const sourceKey = (layer: LayerName): string => (layer === "aircraft" ? "map/aircraft" : "map/ships");

/** The words of one source in the list: None, a service by its own name, or My own receiver. */
function sourceText(source: SourceName): string {
  if (source === "none") return t("layers.settings.none");
  return isService(source) ? SOURCE_NAMES[source] : t("layers.receiver.own");
}

/** The list of a layer: the sources offered in the daemon's order (all of the layer's while the daemon has not said). */
export function sourceChoices(layer: LayerName, offered?: readonly SourceName[]): readonly Choice[] {
  const all: readonly SourceName[] = layer === "aircraft" ? AIRCRAFT_SOURCES : SHIP_SOURCES;
  return (offered ?? all).map((source) => ({ value: source, label: sourceText(source) }));
}

/** The source a row shows: the stored one while it is offered, else None. */
export function shownSource(stored: string, offered: readonly SourceName[] | undefined, layer: LayerName): string {
  const list: readonly string[] = offered ?? (layer === "aircraft" ? AIRCRAFT_SOURCES : SHIP_SOURCES);
  return list.includes(stored) ? stored : "none";
}

/** What the four fields say of themselves (FIELDS of lib/settings.ts); the choices of a source row are all of the layer's here and the offered ones in the form. */
export const LAYER_SPECS: Record<string, FieldSpec> = {
  "map/aircraft": {
    name: "layers.aircraft",
    label: "layers.aircraft",
    kind: "choice",
    choices: () => sourceChoices("aircraft"),
    tipLabel: "layers.settings.aircraft_tip_label",
    tip: ["layers.settings.aircraft_tip1", "layers.settings.aircraft_tip2"],
  },
  "map/ships": {
    name: "layers.ships",
    label: "layers.ships",
    kind: "choice",
    choices: () => sourceChoices("ships"),
    tipLabel: "layers.settings.ships_tip_label",
    tip: ["layers.settings.ships_tip1", "layers.settings.ships_tip2"],
  },
  "map/aircraft_host": {
    label: "layers.receiver.address",
    empty: "layers.receiver.empty",
    tipLabel: "layers.receiver.aircraft_tip_label",
    tip: ["layers.receiver.aircraft_tip1", "layers.receiver.aircraft_tip2"],
  },
  "map/ships_host": {
    label: "layers.receiver.address",
    empty: "layers.receiver.empty",
    tipLabel: "layers.receiver.ships_tip_label",
    tip: ["layers.receiver.ships_tip1", "layers.receiver.ships_tip2"],
  },
};

/** Whether an address field is shown: while the choice of its row (the values the form holds) is My own receiver. */
export function layerShown(key: string, values: Readonly<Record<string, string>>): boolean {
  const own = layerKey(key);
  return own === null || own.role === "source" || values[sourceKey(own.layer)] === "receiver";
}

/** The layer's row of the topic `map`, if the daemon has said it. */
export const layerOf = (layers: readonly MapLayer[] | undefined, layer: LayerName): MapLayer | null => layers?.find((row) => row.layer === layer) ?? null;
