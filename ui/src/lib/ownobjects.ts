// Our objects and items as the page handles them: the form draft, its problems, the command it
// makes and the wording of a list row. The daemon checks everything again (neoaprs/ownobject.py);
// the page only keeps the user from sending what would be refused.
import { t } from "@/i18n";
import { DIRECT, parsePathSetting } from "@/lib/calls";
import { untilText } from "@/lib/format";
import { parseNumber, symbolProblem } from "@/lib/fieldcheck";
import { isPrintable } from "@/lib/messages";
import { degreesText, roundPlace, wrapLongitude } from "@/lib/setup";
import { LIMITS } from "@/protocol/lists";
import type { RadioId } from "@/lib/radios";
import type { Command, OwnObjectRow } from "@/protocol/protocol";

type Kind = OwnObjectRow["kind"];
type ObjectCommand = Extract<Command, { cmd: "object_set" }>;

/** The longest name of an object, and the shortest name of an item. */
export const NAME_MAX = LIMITS.object.nameMax;
const ITEM_NAME_MIN = LIMITS.object.itemNameMin;
const NAME_FORBIDDEN = LIMITS.object.nameForbidden;
/** Characters a comment may not hold (narrower than a name's: `!` and `_` are fine). */
const COMMENT_FORBIDDEN = "|~";

const holds = (text: string, forbidden: string): boolean => [...forbidden].some((c) => text.includes(c));
const SPEED_MAX_KMH = LIMITS.object.speedMaxKmh;
const COURSE_MAX = LIMITS.object.courseMax;
/** The symbol of a new object: the repeater tower. */
const DEFAULT_SYMBOL = "/r";
/** How long past its time an object waits for the radio before the list says so. */
const OVERDUE_MS = 5000;

/**
 * The form's fields as typed. `symbol` is table plus code (`/>`); `path` is empty for the beacon's.
 */
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
  /** The QRU group as typed (sent in capitals), empty for none. */
  qru: string;
  /** Send only when a station asks for it. */
  onRequest: boolean;
  /**
   * The radios it goes out on (Send on), ascending. Empty for a new object not ticked yet, which
   * starts as the last saved object (`status.new_object_radios`). A radio that is off is kept and
   * counts again when it is on (lib/sendon.ts `inForce`).
   */
  radios: RadioId[];
}

type DraftProblems = Partial<Record<keyof ObjectDraft, string>>;

/** A new object: no name or place, the repeater symbol. */
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
    radios: [],
  };
}

/** The draft of an existing object, for editing. */
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
    radios: [...row.radios],
  };
}

/**
 * What is wrong with a name ("" if fine or empty): printable ASCII, no `! _ | ~`, no edge blanks,
 * length limits.
 */
export function nameProblem(name: string, kind: Kind): string {
  if (name === "") return "";
  if (name !== name.trim() || !isPrintable(name) || holds(name, NAME_FORBIDDEN)) return t("objects.problem.name_chars");
  if (name.length > NAME_MAX) return t("objects.problem.at_most", { max: NAME_MAX });
  return kind === "item" && name.length < ITEM_NAME_MIN
    ? t("objects.problem.item_name", { min: ITEM_NAME_MIN, max: NAME_MAX })
    : "";
}

/**
 * What is wrong with a QRU group ("" if fine or empty): letters and digits, not a reserved word.
 */
export function qruProblem(group: string): string {
  const text = group.trim().toUpperCase();
  if (text === "") return "";
  return new RegExp(`^[A-Z0-9]{1,${LIMITS.object.qruGroupMax}}$`).test(text) &&
    !(LIMITS.object.qruReserved as readonly string[]).includes(text)
    ? ""
    : t("objects.problem.qru_group", { max: LIMITS.object.qruGroupMax });
}

const wholeIn = (text: string, min: number, max: number): boolean =>
  /^\d+$/.test(text.trim()) && Number(text) >= min && Number(text) <= max;

/** The comment's length limit: lower when a course or speed precedes it. */
export function commentLimit(draft: ObjectDraft): number {
  return draft.course.trim() === "" && draft.speed.trim() === ""
    ? LIMITS.object.commentMax
    : LIMITS.object.commentMaxMotion;
}

/** What is wrong with each field; empty fields are not flagged here (`draftReady` covers them). */
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
    !isPrintable(comment) || holds(comment, COMMENT_FORBIDDEN)
      ? t("objects.problem.comment_chars")
      : comment.length > commentLimit(draft)
        ? t("objects.problem.at_most", { max: commentLimit(draft) })
        : "",
  );
  set(
    "course",
    draft.course.trim() === "" || wholeIn(draft.course, 0, COURSE_MAX)
      ? ""
      : t("objects.problem.course", { max: COURSE_MAX }),
  );
  const speed = parseNumber(draft.speed);
  set(
    "speed",
    draft.speed.trim() === "" || (speed !== null && speed >= 0 && speed <= SPEED_MAX_KMH)
      ? ""
      : t("objects.problem.speed", { max: SPEED_MAX_KMH }),
  );
  set("path", parsePathSetting(draft.path) === null ? t("route.calls_hint", { max: LIMITS.path.maxCalls }) : "");
  set("qru", qruProblem(draft.qru));
  return found;
}

/** The course one step on (`delta` degrees) round the compass; empty counts as 0. */
export function steppedCourse(text: string, delta: number): string {
  const now = Math.round(parseNumber(text) ?? 0);
  const span = COURSE_MAX + 1;
  return String((((now + delta) % span) + span) % span);
}

/** The speed one step on (`delta` km/h), clamped to 0..max, one decimal kept; empty counts as 0. */
export function steppedSpeed(text: string, delta: number): string {
  const now = parseNumber(text) ?? 0;
  return String(Math.round(Math.min(SPEED_MAX_KMH, Math.max(0, now + delta)) * 10) / 10);
}

/** Whether Save is enabled: name, position and symbol set and no problems. */
export function draftReady(draft: ObjectDraft): boolean {
  return (
    draft.name !== "" &&
    draft.symbol.length === 2 &&
    parseNumber(draft.lat) !== null &&
    parseNumber(draft.lon) !== null &&
    Object.keys(draftProblems(draft)).length === 0
  );
}

/** Whether the object goes out on the radios the command asked for. */
function sameRadios(row: OwnObjectRow, command: ObjectCommand): boolean {
  return row.radios.length === command.radios.length && row.radios.every((id, i) => id === command.radios[i]);
}

/**
 * The command that creates or changes the object; null while the draft is not ready or has no
 * radio. A new object with no radios ticked uses `start` (`status.new_object_radios`).
 */
export function objectCommand(draft: ObjectDraft, start: readonly RadioId[] = []): ObjectCommand | null {
  const lat = parseNumber(draft.lat);
  const lon = parseNumber(draft.lon);
  if (!draftReady(draft) || lat === null || lon === null) return null;
  const setting = parsePathSetting(draft.path);
  const speed = parseNumber(draft.speed);
  const radios = [...(draft.radios.length > 0 ? draft.radios : start)].sort((a, b) => a - b);
  if (radios.length === 0) return null;
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
    path:
      setting === null || setting.kind === "auto" ? null : setting.kind === "direct" ? DIRECT : setting.calls.join(","),
    qru_group: draft.qru.trim().toUpperCase(),
    on_request: draft.onRequest,
    radios,
  };
}

/** Whether the daemon's object matches the command, i.e. the daemon has taken it. */
export function isObjectOf(row: OwnObjectRow, command: ObjectCommand): boolean {
  const near = (a: number | null, b: number | null): boolean =>
    a === null || b === null ? a === b : Math.abs(a - b) < 1e-9;
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
    row.on_request === command.on_request &&
    sameRadios(row, command)
  );
}

/** The command that moves an object (marker dragged): everything unchanged except the place. */
export function moveCommand(row: OwnObjectRow, lat: number, lon: number): ObjectCommand {
  return {
    cmd: "object_set",
    name: row.name,
    kind: row.kind,
    lat: roundPlace(lat),
    lon: wrapLongitude(lon),
    symbol_table: row.symbol_table,
    symbol_code: row.symbol_code,
    comment: row.comment,
    course_deg: row.course_deg,
    speed_kmh: row.speed_kmh,
    path: row.path,
    qru_group: row.qru_group,
    on_request: row.on_request,
    radios: [...row.radios],
  };
}

/** "sent once", "sent 5 times", "not sent yet". */
export function sentText(sent: number): string {
  return t("schedule.sent", { n: sent });
}

/**
 * The list text for an object of ours: how often sent and when next, "waiting" once that time has
 * passed (no call set or radio away), "killing" while its kill goes out, or "sent only when asked".
 */
export function stateText(row: OwnObjectRow, nowMs: number): string {
  if (row.state === "killing") return t("schedule.killing", { n: row.sent });
  if (row.on_request) return t("schedule.on_request");
  const due = row.next_at === null ? NaN : Date.parse(row.next_at);
  if (Number.isNaN(due)) return sentText(row.sent);
  return nowMs - due > OVERDUE_MS
    ? t("schedule.waiting", { n: row.sent })
    : t("schedule.next", { n: row.sent, when: untilText(row.next_at, nowMs) });
}
