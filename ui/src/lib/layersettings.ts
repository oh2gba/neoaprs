// Settings, Map: a box for each layer (Aircraft, Ships) with its source and its receiver's address
// (components/SettingsLayer.vue), and the Ships box's AISStream key. The keys and what each says of
// itself. The offered sources come from the daemon (`map.layers[i].offered`); a stored source not
// among them shows as None. The address field shows only while the choice is an own receiver; the
// key's row keeps its room while it is not, and shows its field while the choice is AISStream.
import type { Choice } from "@/lib/settingchoices";
import type { FieldInfo, FieldSpec } from "@/lib/settings";
import {
  LAYER_NAMES,
  RADARCAPE_NAME,
  SOURCE_NAMES,
  isOwn,
  isService,
  type LayerName,
  type SourceName,
} from "@/lib/layers/sources";
import { lazyText } from "@/lib/lazytext";
import { t } from "@/i18n";
import { AIRCRAFT_SOURCES, SHIP_SOURCES } from "@/protocol/lists";
import type { MapLayer } from "@/protocol/protocol";

const LAYERS = Object.keys(LAYER_NAMES) as LayerName[];

const sourceKey = (layer: LayerName): string => `map/${layer}`;

/**
 * The keys of each layer: the layer each belongs to, and whether it chooses the source or holds an
 * own receiver's address.
 */
type LayerKey = { layer: LayerName; role: "source" | "address" | "key" };
/** The Ships box's key of AISStream. */
export const AISSTREAM_KEY = "map/ships_key";
const KEYS: Readonly<Record<string, LayerKey>> = {
  ...Object.fromEntries(
    LAYERS.flatMap((layer): [string, LayerKey][] => [
      [sourceKey(layer), { layer, role: "source" }],
      [`${sourceKey(layer)}_host`, { layer, role: "address" }],
    ]),
  ),
  [AISSTREAM_KEY]: { layer: "ships", role: "key" },
};

/** The layer a key belongs to and its role, or null for any other key. */
export const layerKey = (key: string): LayerKey | null => KEYS[key] ?? null;

/** The legend of each layer's box, at its source key (`SUBGROUPS` of lib/settings.ts): the layer's name. */
export const LAYER_BOXES = Object.fromEntries(
  LAYERS.map((layer) => [
    sourceKey(layer),
    lazyText({ title: "", tipLabel: "", tip: [] as readonly string[] }, { text: () => t(LAYER_NAMES[layer]) }),
  ]),
);

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
 * What the fields say of themselves (FIELDS of lib/settings.ts); source rows list all of the
 * layer's choices here. The box has the layer's name, so the source row is Source.
 */
export const LAYER_SPECS: Record<string, FieldSpec> = {
  "map/aircraft": {
    name: "layers.aircraft",
    label: "layers.settings.source",
    kind: "choice",
    choices: () => sourceChoices("aircraft"),
    tipLabel: "layers.settings.aircraft_tip_label",
    tip: ["layers.settings.aircraft_tip1", "layers.settings.aircraft_tip2"],
  },
  "map/ships": {
    name: "layers.ships",
    label: "layers.settings.source",
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
  [AISSTREAM_KEY]: {
    label: "layers.aisstream.key",
    empty: () => "",
    kind: "password",
    tipLabel: "layers.aisstream.key_tip_label",
    tip: ["layers.aisstream.key_tip"],
  },
};

/**
 * Whether a row is there: an address while the choice is an own receiver; the key's row (its room
 * kept, its field shown by `keyShown`) while it is not.
 */
export function layerShown(key: string, values: Readonly<Record<string, string>>): boolean {
  const own = layerKey(key);
  if (own === null || own.role === "source") return true;
  const mine = isOwn(values[sourceKey(own.layer)] ?? "");
  return own.role === "address" ? mine : !mine;
}

/** Whether the key's field is shown in its room: while the choice is AISStream. */
export const keyShown = (values: Readonly<Record<string, string>>): boolean =>
  values[sourceKey("ships")] === "aisstream";

/** The layer's row of the topic `map`, if the daemon has sent it. */
export const layerOf = (layers: readonly MapLayer[] | undefined, layer: LayerName): MapLayer | null =>
  layers?.find((row) => row.layer === layer) ?? null;

/**
 * The address field of a row as its source has it: a Radarcape's (i) says what to type and its box
 * has no word; others keep their own.
 */
export function addressField(base: FieldInfo, key: string, values: Readonly<Record<string, string>>): FieldInfo {
  const own = layerKey(key);
  if (own?.role !== "address" || values[sourceKey(own.layer)] !== "radarcape") return base;
  return { ...base, empty: "", tip: [t("layers.receiver.radarcape_tip")] };
}
