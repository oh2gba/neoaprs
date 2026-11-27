// A logged packet as a few plain facts for the click-through detail: sender, kind, content
// (position, text, object name) and how it reached us or which path we sent it by. The raw line and
// decoded JSON stay behind "Raw". Everything here is a plain function of one packet row.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { bearingText, dateTimeText, positionText } from "@/lib/format";
import { packetCameBy, packetTag } from "@/lib/channels";
import { frequencyText, sentTimeText, stormText } from "@/lib/details";
import { routeWords } from "@/lib/routes";
import type { PageRadio } from "@/lib/radios";
import { readingText } from "@/lib/signal";
import { heightText, speedText, tempText } from "@/lib/units";
import type {
  DecodedOther,
  DecodedStatus,
  DecodedUndecoded,
  DecodedWeather,
  PacketRow,
  PositionFields,
} from "@/protocol/protocol";

export interface Fact {
  label: string;
  text: string;
  /**
   * A route: the line may break between words, not inside a callsign (components/RouteText.vue).
   */
  route?: boolean;
}

/**
 * The kinds of "other" packets the daemon names (a non-report telemetry packet is one), with the
 * message for each.
 */
const OTHER: Record<DecodedOther["kind"], MessageId> = {
  weather: "packets.kind.weather",
  capabilities: "packets.kind.capabilities",
  query: "packets.kind.query",
  "third-party": "packets.kind.third_party",
  nmea: "packets.kind.nmea",
  test: "packets.kind.test",
  "agrelo-df": "packets.kind.agrelo_df",
  "user-defined": "packets.kind.user_defined",
  shelter: "packets.kind.shelter",
  "space-weather": "packets.kind.space_weather",
  telemetry: "packets.kind.telemetry",
  unknown: "packets.kind.other",
};

/** Why a packet could not be read, in words, by the daemon's code. */
const WHY: Record<DecodedUndecoded["code"], MessageId> = {
  empty: "packets.why.empty",
  position: "packets.why.position",
  mice: "packets.why.mice",
  message: "packets.why.message",
  nmea: "packets.why.nmea",
  damaged: "packets.why.damaged",
};

/** What kind of packet it is, in words: "Position report", "Message", "Weather report". */
export function kindWords(row: PacketRow): string {
  const d = row.decoded;
  if (d.type === "telemetry") return t("packets.kind.telemetry");
  if (d.type === "other") {
    // a kind from a newer daemon has no words: plain "Other packet"
    const id = OTHER[d.kind] as MessageId | undefined;
    return t(id ?? "packets.kind.other");
  }
  return t(`packets.kind.${row.kind}`);
}

function weatherText(w: DecodedWeather): string {
  const parts = [
    w.temp_c === null ? "" : tempText(w.temp_c),
    w.wind_kmh === null ? "" : t("packets.wind", { speed: speedText(w.wind_kmh) }),
  ];
  return parts.filter((part) => part !== "").join(", ");
}

/**
 * Where, how it moves and what the sender added: the facts of a position in a position report,
 * object or item.
 */
function positionFacts(p: PositionFields): Fact[] {
  const where = positionText(p.lat, p.lon);
  const facts: Fact[] = [
    {
      label: t("station.field.position"),
      text: p.ambiguity > 0 ? t("packets.position_approximate", { position: where }) : where,
    },
  ];
  if (p.speed_kmh !== null && p.speed_kmh > 0) {
    facts.push({
      label: t("station.field.speed"),
      text:
        p.course_deg === null
          ? speedText(p.speed_kmh)
          : t("station.speed_course", { speed: speedText(p.speed_kmh), course: bearingText(p.course_deg) }),
    });
  }
  if (p.altitude_m !== null) facts.push({ label: t("station.field.altitude"), text: heightText(p.altitude_m) });
  if (p.weather !== null && weatherText(p.weather) !== "")
    facts.push({ label: t("packets.fact.weather"), text: weatherText(p.weather) });
  if (p.frequency !== null) facts.push({ label: t("station.field.frequency"), text: frequencyText(p.frequency) });
  if (p.storm !== null) facts.push({ label: t("station.field.storm"), text: stormText(p.storm) });
  if (p.sign !== null) facts.push({ label: t("station.field.sign"), text: p.sign });
  if (p.comment !== "") facts.push({ label: t("station.field.comment"), text: p.comment });
  return facts;
}

/** The frequency a status text began with and what follows it. */
function statusFacts(d: DecodedStatus): Fact[] {
  const facts: Fact[] = [];
  if (d.frequency !== null) facts.push({ label: t("station.field.frequency"), text: frequencyText(d.frequency) });
  if (d.text !== "") facts.push({ label: t("station.field.status"), text: d.text });
  return facts;
}

/** What the packet says, by its kind. */
function contentFacts(row: PacketRow): Fact[] {
  const d = row.decoded;
  switch (d.type) {
    case "position":
      return positionFacts(d);
    case "message":
      if (d.ack_id !== null)
        return [
          { label: t("packets.fact.to"), text: d.addressee },
          { label: t("packets.fact.says"), text: t("packets.says.received", { id: d.ack_id }) },
        ];
      if (d.rej_id !== null)
        return [
          { label: t("packets.fact.to"), text: d.addressee },
          { label: t("packets.fact.says"), text: t("packets.says.refuses", { id: d.rej_id }) },
        ];
      return [
        { label: t("packets.fact.to"), text: d.addressee },
        { label: t("packets.fact.text"), text: d.text },
      ];
    case "object":
    case "item":
      return [
        { label: t("packets.fact.name"), text: d.alive ? d.name : t("packets.object_down", { name: d.name }) },
        ...positionFacts(d.position),
      ];
    case "status":
      return statusFacts(d);
    case "telemetry":
      return d.sequence === null
        ? []
        : [{ label: t("packets.fact.report"), text: t("packets.report_number", { number: d.sequence }) }];
    case "other":
      return d.text === "" ? [] : [{ label: t("packets.fact.text"), text: d.text }];
    case "undecoded": {
      const why = WHY[d.code] as MessageId | undefined; // a code from a newer daemon: the plain word
      return [
        { label: t("packets.fact.why"), text: t(why ?? "packets.why.damaged") },
        { label: t("packets.fact.text"), text: d.text },
      ];
    }
  }
}

/**
 * The one line of a packet in the Summary column: kind and content ("Message · OH2RDG · Hello").
 */
export function summaryText(row: PacketRow): string {
  return [kindWords(row), ...contentFacts(row).map((fact) => fact.text)].join(" · ");
}

/**
 * The facts of a packet in telling order: from, kind, content, how it travelled ("Came by": its tag
 * and meaning, "Packet - heard on radio Packet"), when. `radios` is every radio in box order.
 */
export function packetFacts(row: PacketRow, radios: readonly PageRadio[] = []): Fact[] {
  const known = radios;
  const facts: Fact[] = [
    { label: t("packets.fact.from"), text: row.source },
    { label: t("packets.fact.kind"), text: kindWords(row) },
    ...contentFacts(row),
  ];
  if (row.direction === "out")
    facts.push({
      label: t("packets.fact.sent_via"),
      text: row.path.length === 0 ? t("route.direct") : row.path.join(","),
    });
  else {
    const tag = packetTag(row, known);
    const what = packetCameBy(row, known);
    if (tag !== null && what !== null)
      facts.push({ label: t("packets.fact.came"), text: t("packets.fact.came_value", { channel: tag.label, what }) });
    if (row.route !== "") facts.push({ label: t("station.field.reached"), text: routeWords(row.route), route: true });
    else if (row.via === "is" && row.path.length > 0)
      facts.push({ label: t("station.field.path"), text: row.path.join(",") });
  }
  const signal = row.direction === "in" ? readingText(row) : null;
  if (signal !== null) facts.push({ label: t("packets.fact.signal"), text: signal });
  facts.push({
    label: row.direction === "out" ? t("packets.fact.sent") : t("packets.fact.heard"),
    text: dateTimeText(row.heard_at),
  });
  const carried = sentTimeText(row);
  if (carried !== null) facts.push({ label: t("packets.fact.time_in_packet"), text: carried });
  return facts;
}
