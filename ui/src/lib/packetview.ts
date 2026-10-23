// A packet of the log told in a few plain facts, for the detail a click opens: who sent it, what kind of packet it is, what it says (the position, the text, the object's name), and how it reached us or which path we sent it by. The raw line and the decoded JSON stay
// behind "Raw" for the few who want them. Everything here is a plain function of one packet row.
import { altitudeText, bearingText, dateTimeText, positionText, speedText } from "@/lib/format";
import { sentTimeText } from "@/lib/details";
import { tempText, windSpeedText } from "@/lib/weather";
import type { DecodedWeather, PacketRow, PositionFields } from "@/protocol/protocol";

export interface Fact {
  label: string;
  text: string;
  /** a route: the line may break between the words, not in a callsign (components/RouteText.vue) */
  route?: boolean;
}

const KINDS: Record<PacketRow["kind"], string> = {
  position: "Position report",
  message: "Message",
  object: "Object",
  item: "Item",
  status: "Status report",
  other: "Other packet",
  undecoded: "Could not be read",
};

const OTHER: Record<string, string> = {
  weather: "Weather report",
  telemetry: "Telemetry report",
  capabilities: "Station capabilities",
  query: "Query",
  "third-party": "Third-party packet",
  nmea: "GPS sentence",
  test: "Test packet",
};

/** What kind of packet it is, in words: "Position report", "Message", "Weather report". */
export function kindWords(row: PacketRow): string {
  const d = row.decoded;
  if (d.type === "telemetry") return OTHER.telemetry ?? "";
  if (d.type === "other") return OTHER[d.kind] ?? `Other packet (${d.kind})`;
  return KINDS[row.kind];
}

function weatherText(w: DecodedWeather): string {
  const parts = [w.temp_c === null ? "" : tempText(w.temp_c), w.wind_kmh === null ? "" : `wind ${windSpeedText(w.wind_kmh)}`];
  return parts.filter((part) => part !== "").join(", ");
}

/** Where, how it moves and what the sender added: the facts of a position that is part of a position report, an object or an item. */
function positionFacts(p: PositionFields): Fact[] {
  const facts: Fact[] = [{ label: "Position", text: `${positionText(p.lat, p.lon)}${p.ambiguity > 0 ? " (approximate)" : ""}` }];
  if (p.speed_kmh !== null && p.speed_kmh > 0) {
    facts.push({ label: "Speed", text: p.course_deg === null ? speedText(p.speed_kmh) : `${speedText(p.speed_kmh)}, course ${bearingText(p.course_deg)}` });
  }
  if (p.altitude_m !== null) facts.push({ label: "Altitude", text: altitudeText(p.altitude_m) });
  if (p.weather !== null && weatherText(p.weather) !== "") facts.push({ label: "Weather", text: weatherText(p.weather) });
  if (p.comment !== "") facts.push({ label: "Comment", text: p.comment });
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
          { label: "To", text: d.addressee },
          { label: "Says", text: `received message ${d.ack_id}` },
        ];
      if (d.rej_id !== null)
        return [
          { label: "To", text: d.addressee },
          { label: "Says", text: `refuses message ${d.rej_id}` },
        ];
      return [
        { label: "To", text: d.addressee },
        { label: "Text", text: d.text },
      ];
    case "object":
    case "item":
      return [{ label: "Name", text: `${d.name}${d.alive ? "" : " (taken down)"}` }, ...positionFacts(d.position)];
    case "status":
      return [{ label: "Status", text: d.text }];
    case "telemetry":
      return d.sequence === null ? [] : [{ label: "Report", text: `number ${d.sequence}` }];
    case "other":
      return d.text === "" ? [] : [{ label: "Text", text: d.text }];
    case "undecoded":
      return [
        { label: "Why", text: d.error },
        { label: "Text", text: d.text },
      ];
  }
}

/** The facts of a packet, in the order they are told: from, kind, what it says, how it travelled, when. */
export function packetFacts(row: PacketRow): Fact[] {
  const facts: Fact[] = [{ label: "From", text: row.source }, { label: "Kind", text: kindWords(row) }, ...contentFacts(row)];
  if (row.direction === "out") facts.push({ label: "Sent via", text: row.path.length === 0 ? "direct" : row.path.join(",") });
  else if (row.route !== "") facts.push({ label: "Reached us", text: row.route, route: true });
  facts.push({ label: row.direction === "out" ? "Sent" : "Heard", text: dateTimeText(row.heard_at) });
  const carried = sentTimeText(row);
  if (carried !== null) facts.push({ label: "Time in the packet", text: carried });
  return facts;
}
