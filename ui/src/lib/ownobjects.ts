// Our objects and items as the page handles them: the draft of the form (every field as it is typed), what is wrong with it, the command it makes, and how a row of the list is worded. The daemon checks
// all of it again (neoaprs/ownobject.py); the page only keeps the user from sending what it would refuse, and says what is wrong in the title of the field.
import { t } from "@/i18n";
import { DIRECT, parsePathSetting } from "@/lib/calls";
import { untilText } from "@/lib/format";
import { parseNumber, symbolProblem } from "@/lib/fieldcheck";
import { degreesText } from "@/lib/setup";
import { LIMITS } from "@/protocol/lists";
import type { Command, OwnObjectRow } from "@/protocol/protocol";

type Kind = OwnObjectRow["kind"];
type ObjectCommand = Extract<Command, { cmd: "object_set" }>;

/** The longest name of an object and the shortest and longest of an item. */
export const NAME_MAX = LIMITS.object.nameMax;
const ITEM_NAME_MIN = LIMITS.object.itemNameMin;
const NAME_FORBIDDEN = LIMITS.object.nameForbidden;
const SPEED_MAX_KMH = LIMITS.object.speedMaxKmh;
const COURSE_MAX = LIMITS.object.courseMax;
/** The symbol a new object has: the repeater (the antenna tower), for what objects are mostly used for: a local repeater or frequency, an event, a node or a net. */
const DEFAULT_SYMBOL = "/r";
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
  /** The QRU group (as typed: it is sent in capitals), empty for none. */
  qru: string;
  /** Send only when a station asks for it. */
  onRequest: boolean;
}

type DraftProblems = Partial<Record<keyof ObjectDraft, string>>;

/** A new object: no name and no place (the user picks one), the repeater as its symbol. */
export function emptyDraft(): ObjectDraft {
  return {
    name: "",
    kind: "object",
    symbol: DEFAULT_SYMBOL,
    lat: "",
    lon: "",
    comment: "",
    course: "",
    speed: "",
    path: "",
    qru: "",
    onRequest: false,
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
    qru: row.qru_group,
    onRequest: row.on_request,
  };
}

/** What is wrong with a name, "" when it is fine or empty: 1 to 9 characters (an item 3 to 9) of printable ASCII, none of `! _ | ~`, no blank at either end. */
export function nameProblem(name: string, kind: Kind): string {
  if (name === "") return "";
  if (name !== name.trim() || !/^[\x20-\x7e]*$/.test(name) || [...NAME_FORBIDDEN].some((c) => name.includes(c))) return t("objects.problem.name_chars");
  if (name.length > NAME_MAX) return t("objects.problem.at_most", { max: NAME_MAX });
  return kind === "item" && name.length < ITEM_NAME_MIN ? t("objects.problem.item_name", { min: ITEM_NAME_MIN, max: NAME_MAX }) : "";
}

/** What is wrong with a QRU group, "" when it is fine or empty: 1 to 8 letters and digits, and not one of the words QRU takes for something else. */
export function qruProblem(group: string): string {
  const text = group.trim().toUpperCase();
  if (text === "") return "";
  return new RegExp(`^[A-Z0-9]{1,${LIMITS.object.qruGroupMax}}$`).test(text) && !(LIMITS.object.qruReserved as readonly string[]).includes(text)
    ? ""
    : t("objects.problem.qru_group", { max: LIMITS.object.qruGroupMax });
}

const wholeIn = (text: string, min: number, max: number): boolean => /^\d+$/.test(text.trim()) && Number(text) >= min && Number(text) <= max;

/** How many characters the comment may have: fewer when a course or speed goes in front of it. */
export function commentLimit(draft: ObjectDraft): number {
  return draft.course.trim() === "" && draft.speed.trim() === "" ? LIMITS.object.commentMax : LIMITS.object.commentMaxMotion;
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
    ["lat", LIMITS.range["station/lat"].max],
    ["lon", LIMITS.range["station/lon"].max],
  ] as const) {
    const value = parseNumber(draft[field]);
    set(
      field,
      draft[field].trim() === ""
        ? ""
        : value === null
          ? t("objects.problem.not_number")
          : Math.abs(value) <= limit
            ? ""
            : t("objects.problem.between", { max: limit }),
    );
  }
  const comment = draft.comment.trim();
  set(
    "comment",
    !/^[\x20-\x7e]*$/.test(comment) || /[|~]/.test(comment)
      ? t("objects.problem.comment_chars")
      : comment.length > commentLimit(draft)
        ? t("objects.problem.at_most", { max: commentLimit(draft) })
        : "",
  );
  set("course", draft.course.trim() === "" || wholeIn(draft.course, 0, COURSE_MAX) ? "" : t("objects.problem.course", { max: COURSE_MAX }));
  const speed = parseNumber(draft.speed);
  set("speed", draft.speed.trim() === "" || (speed !== null && speed >= 0 && speed <= SPEED_MAX_KMH) ? "" : t("objects.problem.speed", { max: SPEED_MAX_KMH }));
  set("path", parsePathSetting(draft.path) === null ? t("route.calls_hint", { max: LIMITS.path.maxCalls }) : "");
  set("qru", qruProblem(draft.qru));
  return found;
}

/** The course one step on from the text (`delta` degrees, up or down), round the compass: up from 359 is 0, down from 0 is 359; empty counts as 0. Whole degrees. */
export function steppedCourse(text: string, delta: number): string {
  const now = Math.round(parseNumber(text) ?? 0);
  const span = COURSE_MAX + 1;
  return String((((now + delta) % span) + span) % span);
}

/** The speed one step on (`delta` km/h), between 0 and the most an object may say; empty counts as 0; a tenth is kept. */
export function steppedSpeed(text: string, delta: number): string {
  const now = parseNumber(text) ?? 0;
  return String(Math.round(Math.min(SPEED_MAX_KMH, Math.max(0, now + delta)) * 10) / 10);
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
  const setting = parsePathSetting(draft.path);
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
    path: setting === null || setting.kind === "auto" ? null : setting.kind === "direct" ? DIRECT : setting.calls.join(","),
    qru_group: draft.qru.trim().toUpperCase(),
    on_request: draft.onRequest,
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
    row.path === command.path &&
    row.qru_group === command.qru_group &&
    row.on_request === command.on_request
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
    qru_group: row.qru_group,
    on_request: row.on_request,
  };
}

/** A longitude brought into -180 to 180, five decimals (a metre). */
export function wrapLongitude(lon: number): number {
  return Math.round((((((lon + 180) % 360) + 360) % 360) - 180) * 1e5) / 1e5;
}

/** "sent once", "sent 5 times", "not sent yet". */
export function sentText(sent: number): string {
  return t("schedule.sent", { n: sent });
}

/** What the list says of an object of ours: how often it was sent and when it is sent next, "waiting" when that time has passed (the call is not set or the radio is away), "killing" for one whose kill is going out, "sent only when asked" for one that is never sent on the schedule. */
export function stateText(row: OwnObjectRow, nowMs: number): string {
  if (row.state === "killing") return t("schedule.killing", { n: row.sent });
  if (row.on_request) return t("schedule.on_request");
  const due = row.next_at === null ? NaN : Date.parse(row.next_at);
  if (Number.isNaN(due)) return sentText(row.sent);
  return nowMs - due > OVERDUE_MS ? t("schedule.waiting", { n: row.sent }) : t("schedule.next", { n: row.sent, when: untilText(row.next_at, nowMs) });
}
