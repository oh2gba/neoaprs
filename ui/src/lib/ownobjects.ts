// Our objects and items as the page handles them: the draft of the form (every field as it is typed), what is wrong with it, the command it makes, and how a row of the list is worded. The daemon checks
// all of it again (neoaprs/ownobject.py); the page only keeps the user from sending what it would refuse, and says what is wrong in the title of the field.
import { parsePath } from "@/lib/calls";
import { untilText } from "@/lib/format";
import { degreesText, parseNumber, symbolProblem } from "@/lib/setup";
import type { Command, OwnObjectRow } from "@/protocol/protocol";

type Kind = OwnObjectRow["kind"];
type ObjectCommand = Extract<Command, { cmd: "object_set" }>;

/** The longest name of an object and the shortest and longest of an item (OBJECT_NAME and ITEM_NAME of neoaprs/ownobject.py). */
export const NAME_MAX = 9;
const ITEM_NAME_MIN = 3;
const NAME_FORBIDDEN = "!_|~";
/** The comment of an object: 43 characters, 36 behind a course and speed (COMMENT_MAX and COMMENT_MAX_MOTION). */
export const COMMENT_MAX = 43;
export const COMMENT_MAX_MOTION = 36;
const SPEED_MAX_KMH = 1850;
/** The symbol a new object has: the car, which is what the map shows for something that moves. */
const DEFAULT_SYMBOL = "/>";
/** How long past its time an object waits for the radio before the list says so. */
const OVERDUE_MS = 5000;

/** What the form holds: every field as it is typed. `symbol` is the table character and the code character (`/>`), `path` empty for the beacon's. */
export interface ObjectDraft {
  name: string;
  kind: Kind;
  symbol: string;
  lat: string;
  lon: string;
  comment: string;
  course: string;
  speed: string;
  path: string;
}

type DraftProblems = Partial<Record<keyof ObjectDraft, string>>;

/** A new object: where we are (when we are anywhere), the car, no name. */
export function emptyDraft(at: { lat: number; lon: number } | null): ObjectDraft {
  return {
    name: "",
    kind: "object",
    symbol: DEFAULT_SYMBOL,
    lat: at === null ? "" : degreesText(at.lat),
    lon: at === null ? "" : degreesText(at.lon),
    comment: "",
    course: "",
    speed: "",
    path: "",
  };
}

/** The draft of an object the daemon has, to change it. */
export function draftOf(row: OwnObjectRow): ObjectDraft {
  return {
    name: row.name,
    kind: row.kind,
    symbol: `${row.symbol_table}${row.symbol_code}`,
    lat: degreesText(row.lat),
    lon: degreesText(row.lon),
    comment: row.comment,
    course: row.course_deg === null ? "" : String(row.course_deg),
    speed: row.speed_kmh === null ? "" : String(Math.round(row.speed_kmh * 10) / 10),
    path: row.path ?? "",
  };
}

/** What is wrong with a name, "" when it is fine or empty: 1 to 9 characters (an item 3 to 9) of printable ASCII, none of `! _ | ~`, no blank at either end. */
export function nameProblem(name: string, kind: Kind): string {
  if (name === "") return "";
  if (name !== name.trim() || !/^[\x20-\x7e]*$/.test(name) || [...NAME_FORBIDDEN].some((c) => name.includes(c)))
    return "No blank at either end, none of ! _ | ~";
  if (name.length > NAME_MAX) return `At most ${NAME_MAX} characters`;
  return kind === "item" && name.length < ITEM_NAME_MIN ? `An item has ${ITEM_NAME_MIN} to ${NAME_MAX} characters` : "";
}

const wholeIn = (text: string, min: number, max: number): boolean => /^\d+$/.test(text.trim()) && Number(text) >= min && Number(text) <= max;

/** How many characters the comment may have: fewer when a course or speed goes in front of it. */
export function commentLimit(draft: ObjectDraft): number {
  return draft.course.trim() === "" && draft.speed.trim() === "" ? COMMENT_MAX : COMMENT_MAX_MOTION;
}

/** What is wrong with each field as it stands (the empty ones are not wrong here: `draftReady` says what is still needed). */
export function draftProblems(draft: ObjectDraft): DraftProblems {
  const found: DraftProblems = {};
  const set = (field: keyof ObjectDraft, text: string): void => {
    if (text !== "") found[field] = text;
  };
  set("name", nameProblem(draft.name, draft.kind));
  set("symbol", symbolProblem(draft.symbol));
  for (const [field, limit] of [
    ["lat", 90],
    ["lon", 180],
  ] as const) {
    const value = parseNumber(draft[field]);
    set(field, draft[field].trim() === "" ? "" : value === null ? "Not a number" : Math.abs(value) <= limit ? "" : `Between -${limit} and ${limit}`);
  }
  const comment = draft.comment.trim();
  set(
    "comment",
    !/^[\x20-\x7e]*$/.test(comment) || /[|~]/.test(comment)
      ? "Printable ASCII, no | or ~"
      : comment.length > commentLimit(draft)
        ? `At most ${commentLimit(draft)} characters`
        : "",
  );
  set("course", draft.course.trim() === "" || wholeIn(draft.course, 0, 359) ? "" : "0 to 359 degrees");
  const speed = parseNumber(draft.speed);
  set("speed", draft.speed.trim() === "" || (speed !== null && speed >= 0 && speed <= SPEED_MAX_KMH) ? "" : `0 to ${SPEED_MAX_KMH} km/h`);
  set("path", parsePath(draft.path) === null ? "Calls separated by commas, at most 8" : "");
  return found;
}

/** Whether Save is on: a name, a position and a symbol, and nothing wrong. */
export function draftReady(draft: ObjectDraft): boolean {
  return (
    draft.name !== "" &&
    draft.symbol.length === 2 &&
    parseNumber(draft.lat) !== null &&
    parseNumber(draft.lon) !== null &&
    Object.keys(draftProblems(draft)).length === 0
  );
}

/** The command that makes or changes the object; null while the draft is not ready. */
export function objectCommand(draft: ObjectDraft): ObjectCommand | null {
  const lat = parseNumber(draft.lat);
  const lon = parseNumber(draft.lon);
  if (!draftReady(draft) || lat === null || lon === null) return null;
  const path = parsePath(draft.path) ?? [];
  const speed = parseNumber(draft.speed);
  return {
    cmd: "object_set",
    name: draft.name,
    kind: draft.kind,
    lat,
    lon,
    symbol_table: draft.symbol.slice(0, 1),
    symbol_code: draft.symbol.slice(1),
    comment: draft.comment.trim(),
    course_deg: draft.course.trim() === "" ? null : Number(draft.course),
    speed_kmh: speed === null ? null : speed,
    path: path.length === 0 ? null : path.join(","),
  };
}

/** Whether the object the daemon has is what the command asked for (so the daemon has taken it). */
export function isObjectOf(row: OwnObjectRow, command: ObjectCommand): boolean {
  const near = (a: number | null, b: number | null): boolean => (a === null || b === null ? a === b : Math.abs(a - b) < 1e-9);
  return (
    row.name === command.name &&
    row.kind === command.kind &&
    near(row.lat, command.lat) &&
    near(row.lon, command.lon) &&
    row.symbol_table === command.symbol_table &&
    row.symbol_code === command.symbol_code &&
    row.comment === command.comment &&
    row.course_deg === command.course_deg &&
    near(row.speed_kmh, command.speed_kmh) &&
    row.path === command.path
  );
}

/** The command that puts an object where the map says (the marker was dragged): everything as it is, the place new. */
export function moveCommand(row: OwnObjectRow, lat: number, lon: number): ObjectCommand {
  return {
    cmd: "object_set",
    name: row.name,
    kind: row.kind,
    lat: Math.round(lat * 1e5) / 1e5,
    lon: wrapLongitude(lon),
    symbol_table: row.symbol_table,
    symbol_code: row.symbol_code,
    comment: row.comment,
    course_deg: row.course_deg,
    speed_kmh: row.speed_kmh,
    path: row.path,
  };
}

/** A longitude brought into -180 to 180, five decimals (a metre). */
export function wrapLongitude(lon: number): number {
  return Math.round((((((lon + 180) % 360) + 360) % 360) - 180) * 1e5) / 1e5;
}

/** "sent twice", "sent 5 times", "not sent yet". */
export function sentText(sent: number): string {
  return sent === 0 ? "not sent yet" : sent === 1 ? "sent once" : `sent ${sent} times`;
}

/** What the list says of an object of ours: how often it was sent and when it is sent next, "waiting" when that time has passed (the call is not set or the radio is away), "killing" for one whose kill is going out. */
export function stateText(row: OwnObjectRow, nowMs: number): string {
  if (row.state === "killing") return `killing, ${sentText(row.sent)}`;
  const due = row.next_at === null ? NaN : Date.parse(row.next_at);
  const next = Number.isNaN(due) ? "" : nowMs - due > OVERDUE_MS ? ", waiting" : `, next ${untilText(row.next_at, nowMs)}`;
  return `${sentText(row.sent)}${next}`;
}
