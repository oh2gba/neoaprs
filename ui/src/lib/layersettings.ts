// Settings, Map: the Aircraft and Ships rows and each one's receiver address
// (components/SettingsLayer.vue). The four keys and what each says of itself. The offered sources
// come from the daemon (`map.layers[i].offered`); a stored source not among them shows as None. The
// address field shows only while the row's choice is an own receiver.
import type { Choice } from "@/lib/settingchoices";
import type { FieldInfo, FieldSpec } from "@/lib/settings";
import { RADARCAPE_NAME, SOURCE_NAMES, isOwn, isService, type LayerName, type SourceName } from "@/lib/layers/sources";
import { t } from "@/i18n";
import { AIRCRAFT_SOURCES, SHIP_SOURCES } from "@/protocol/lists";
import type { MapLayer } from "@/protocol/protocol";

/**
 * The four keys: the layer each belongs to, and whether it chooses the source or holds an own
 * receiver's address.
 */
const KEYS: Readonly<Record<string, { layer: LayerName; role: "source" | "address" }>> = {
  "map/aircraft": { layer: "aircraft", role: "source" },
  "map/aircraft_host": { layer: "aircraft", role: "address" },
  "map/ships": { layer: "ships", role: "source" },
  "map/ships_host": { layer: "ships", role: "address" },
};

/** The layer a key belongs to and its role, or null for any other key. */
export const layerKey = (key: string): { layer: LayerName; role: "source" | "address" } | null => KEYS[key] ?? null;

const sourceKey = (layer: LayerName): string => (layer === "aircraft" ? "map/aircraft" : "map/ships");

/**
 * The words of one source in the list: None, a service or the Radarcape by name, or My own
 * receiver.
 */
function sourceText(source: SourceName): string {
  if (source === "none") return t("layers.settings.none");
  if (source === "radarcape") return RADARCAPE_NAME;
  if (isService(source)) return SOURCE_NAMES[source];
  return t("layers.receiver.own");
}

/**
 * A layer's list: the sources offered, in the daemon's order (all of the layer's until the daemon
 * has said).
 */
export function sourceChoices(layer: LayerName, offered?: readonly SourceName[]): readonly Choice[] {
  const all: readonly SourceName[] = layer === "aircraft" ? AIRCRAFT_SOURCES : SHIP_SOURCES;
  return (offered ?? all).map((source) => ({ value: source, label: sourceText(source) }));
}

/** The source a row shows: the stored one while it is offered, else None. */
export function shownSource(stored: string, offered: readonly SourceName[] | undefined, layer: LayerName): string {
  const list: readonly string[] = offered ?? (layer === "aircraft" ? AIRCRAFT_SOURCES : SHIP_SOURCES);
  return list.includes(stored) ? stored : "none";
}

/**
 * What the four fields say of themselves (FIELDS of lib/settings.ts); source rows list all of the
 * layer's choices here.
 */
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

/** Whether an address field is shown: while the row's choice is an own receiver. */
export function layerShown(key: string, values: Readonly<Record<string, string>>): boolean {
  const own = layerKey(key);
  return own === null || own.role === "source" || isOwn(values[sourceKey(own.layer)] ?? "");
}

/** The layer's row of the topic `map`, if the daemon has sent it. */
export const layerOf = (layers: readonly MapLayer[] | undefined, layer: LayerName): MapLayer | null => layers?.find((row) => row.layer === layer) ?? null;

/**
 * The address field of a row as its source has it: a Radarcape's (i) says what to type and its box
 * has no word; others keep their own.
 */
export function addressField(base: FieldInfo, key: string, values: Readonly<Record<string, string>>): FieldInfo {
  const own = layerKey(key);
  if (own?.role !== "address" || values[sourceKey(own.layer)] !== "radarcape") return base;
  return { ...base, empty: "", tip: [t("layers.receiver.radarcape_tip")] };
}
