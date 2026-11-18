// What the card of an aircraft or a ship on the map says (components/LayerCard.vue), and its hover box (lib/hovercard.ts): only what its source told, a row only where it has something, in the page's own words and
// formats. An aircraft: its flight, else its registration, else its address in capitals, as the title; the registration beside a flight, the type, where it came from and where it goes, the altitude, the vertical speed, the speed, the heading and the age of its position.
// A ship: its name, else its MMSI; its kind (lib/layers/shipkinds.ts), speed, course, destination and age. The card ends with the source's name. Nothing of a station: no path, no packets, no message.
import { t } from "@/i18n";
import { ageText, altitudeText, bearingText, speedText, verticalText } from "@/lib/format";
import { LAYER_NAMES, RADARCAPE_NAME, SOURCE_NAMES, isService, type LayerName, type SourceName } from "@/lib/layers/sources";
import { shipKind } from "@/lib/layers/shipkinds";
import type { LayerThing } from "@/protocol/protocol";

export interface ThingRow {
  label: string;
  text: string;
}

/** The card's title: what the thing is called. */
export function thingTitle(layer: LayerName, thing: LayerThing): string {
  if (layer === "ships") return thing.name || t("layers.card.mmsi", { id: thing.id });
  return thing.name || thing.registration || thing.id.toUpperCase();
}

/** The muted line under the title: what kind of thing it is. */
export const thingSub = (layer: LayerName): string => (layer === "aircraft" ? t(LAYER_NAMES.aircraft) : t("layers.card.ship"));

/** The source's name as the card ends with it: a service or the Radarcape by its own name, any other receiver as My own receiver. */
const sourceText = (source: SourceName): string =>
  isService(source) ? SOURCE_NAMES[source] : source === "radarcape" ? RADARCAPE_NAME : t("layers.receiver.own");

type Part = readonly [label: string, text: string | null];

const rowsOf = (parts: readonly Part[]): ThingRow[] => parts.flatMap(([label, text]) => (text === null || text === "" ? [] : [{ label, text }]));
const or = <T>(value: T | null, text: (v: T) => string): string | null => (value === null ? null : text(value));

const altitude = (thing: LayerThing): Part => [t("station.field.altitude"), or(thing.altitude_m, altitudeText)];
const vertical = (thing: LayerThing): Part => [t("layers.card.vertical"), or(thing.vertical_ms, verticalText)];
const speed = (thing: LayerThing): Part => [t("station.field.speed"), or(thing.speed_kmh, speedText)];
const age = (thing: LayerThing, nowMs: number): Part => [t("layers.card.age"), ageText(thing.at, nowMs)];
const course = (thing: LayerThing): Part => [t("objects.field.course"), or(thing.course_deg, bearingText)];
const destination = (thing: LayerThing): Part => [t("layers.card.destination"), thing.destination];

/** An airport as the card says it: the place and its code in brackets, the code alone where the table has no place, nothing where there is no code. */
const airport = (code: string, place: string): string => (code === "" ? "" : place === "" ? code : `${place} (${code})`);
const from = (thing: LayerThing): Part => [t("layers.card.from"), airport(thing.origin, thing.origin_place)];
const to = (thing: LayerThing): Part => [t("layers.card.to"), airport(thing.destination, thing.destination_place)];

/** The card's rows, the source last. */
export function cardRows(layer: LayerName, thing: LayerThing, source: SourceName, nowMs: number): ThingRow[] {
  const kind = shipKind(thing.ship_type);
  const parts: Part[] =
    layer === "aircraft"
      ? [
          [t("layers.card.registration"), thing.name !== "" ? thing.registration : null],
          [t("layers.card.type"), thing.type],
          from(thing),
          to(thing),
          altitude(thing),
          vertical(thing),
          speed(thing),
          [t("layers.card.heading"), or(thing.heading_deg, bearingText)],
          age(thing, nowMs),
        ]
      : [[t("station.field.kind"), kind === null ? null : t(kind)], speed(thing), course(thing), destination(thing), age(thing, nowMs)];
  return [...rowsOf(parts), { label: t("layers.card.source"), text: sourceText(source) }];
}

/** The hover box's rows: the few facts at a glance. */
export function hoverRows(layer: LayerName, thing: LayerThing, nowMs: number): ThingRow[] {
  return rowsOf(
    layer === "aircraft" ? [altitude(thing), speed(thing), age(thing, nowMs)] : [speed(thing), course(thing), destination(thing), age(thing, nowMs)],
  );
}
