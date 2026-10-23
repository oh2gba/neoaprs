// The beacon as it would go on the air, for the preview on the Beacon tab: our position packet in TNC2 text, made from the settings the form holds the way the daemon makes it
// (neoaprs/services/beacon.py): `=` for a station with messaging, the position uncompressed (degrees and minutes to the hundredth) or compressed, the symbol, the PHG extension when a power is set, then
// the comment, and `!Wxy!` (DAO) after it when asked; and the status report
// that follows each beacon when the status is not empty: `>`, the day, hour and minute in UTC and `z`, then the text.
// The daemon checks the settings again; this only shows what they would make, and null while they do not make a packet.
import { callList, validCall } from "@/lib/calls";
import { SYMBOL_TABLES } from "@/protocol/lists";

const HUNDREDTHS_PER_DEGREE = 6000;
const THOUSANDTHS_PER_DEGREE = 60000;
const FEET_PER_METRE = 3.2808;
/** The directivity digit of PHG is the place in this list. */
const DIRECTIONS = ["omni", "NE", "E", "SE", "S", "SW", "W", "NW", "N"];
const BASE91_CELLS = 91 ** 4;
const COMPRESSED_LAT_SCALE = 380926;
const COMPRESSED_LON_SCALE = 190463;

/** DDMM.mmN or DDDMM.mmE: the minutes rounded to hundredths (a rounding that reaches 60 minutes carries into the degrees); with `dao` the thousandths digit is left to the DAO and the hundredths are cut. */
function coordinate(value: number, wholeDigits: number, negative: string, positive: string, dao: boolean): string {
  const thousandths = Math.round(Math.abs(value) * THOUSANDTHS_PER_DEGREE);
  const total = dao ? Math.floor(thousandths / 10) : Math.round(Math.abs(value) * HUNDREDTHS_PER_DEGREE);
  const degrees = Math.floor(total / HUNDREDTHS_PER_DEGREE);
  const rest = total % HUNDREDTHS_PER_DEGREE;
  const minutes = String(Math.floor(rest / 100)).padStart(2, "0");
  const hundredths = String(rest % 100).padStart(2, "0");
  return `${String(degrees).padStart(wholeDigits, "0")}${minutes}.${hundredths}${value < 0 && (dao ? thousandths : total) > 0 ? negative : positive}`;
}

/** The 19 characters of an uncompressed position: latitude, symbol table, longitude, symbol code. */
export function uncompressedPosition(lat: number, lon: number, table: string, code: string, dao = false): string {
  return `${coordinate(lat, 2, "S", "N", dao)}${table}${coordinate(lon, 3, "W", "E", dao)}${code}`;
}

/** The DAO extension `!Wxy!`: the digit after the hundredths of the minutes of the latitude and of the longitude. */
export function daoText(lat: number, lon: number): string {
  const digit = (value: number): number => Math.round(Math.abs(value) * THOUSANDTHS_PER_DEGREE) % 10;
  return `!W${digit(lat)}${digit(lon)}!`;
}

/** The PHG extension `PHGphgd`: p the square root of the watts, h the base-2 logarithm of the height in tens of feet (each rounded, 0 to 9), g the gain in dB, d the directivity (0 omni, 1 NE ... 8 N). */
export function phgText(powerW: number, heightM: number, gainDb: number, direction: string): string {
  const p = Math.min(9, Math.floor(Math.sqrt(powerW) + 0.5));
  const feet = heightM * FEET_PER_METRE;
  const h = feet <= 10 ? 0 : Math.min(9, Math.floor(Math.log2(feet / 10) + 0.5));
  return `PHG${p}${h}${Math.min(9, Math.max(0, gainDb))}${DIRECTIONS.indexOf(direction)}`;
}

function base91(value: number): string {
  return [3, 2, 1, 0].map((i) => String.fromCharCode(33 + (Math.floor(value / 91 ** i) % 91))).join("");
}

/** The 13 characters of a compressed position without course, speed or altitude. Overlays 0-9 are written a-j, so that the first character is never a digit. */
export function compressedPosition(lat: number, lon: number, table: string, code: string): string {
  const y = Math.min(Math.max(Math.round((90 - lat) * COMPRESSED_LAT_SCALE), 0), BASE91_CELLS - 1);
  const x = Math.min(Math.max(Math.round((180 + lon) * COMPRESSED_LON_SCALE), 0), BASE91_CELLS - 1);
  const first = /^[0-9]$/.test(table) ? String.fromCharCode(table.charCodeAt(0) - 48 + 97) : table;
  return `${first}${base91(y)}${base91(x)}${code}  A`;
}

function number(text: string | undefined, low: number, high: number): number | null {
  if (text === undefined || text.trim() === "") return null;
  const value = Number(text);
  return Number.isFinite(value) && value >= low && value <= high ? value : null;
}

function whole(text: string | undefined, low: number, high: number): number | null {
  const value = number(text, low, high);
  return value !== null && Number.isInteger(value) ? value : null;
}

/** The PHG of the settings: "" while no power is set, null when the antenna's figures are no figures, else `PHGphgd`. */
function phg(values: Readonly<Record<string, string>>): string | null {
  if ((values["beacon/power_w"] ?? "").trim() === "") return "";
  const power = whole(values["beacon/power_w"], 0, 9999);
  const height = whole(values["beacon/antenna_height_m"], 0, 9999);
  const gain = whole(values["beacon/antenna_gain_db"], 0, 9);
  const direction = (values["beacon/antenna_direction"] ?? "").trim();
  const known = DIRECTIONS.find((d) => d.toLowerCase() === direction.toLowerCase());
  return power === null || height === null || gain === null || known === undefined ? null : phgText(power, height, gain, known);
}

function validSymbol(table: string, code: string): boolean {
  return table.length === 1 && SYMBOL_TABLES.includes(table) && code.length === 1 && code >= "!" && code <= "~";
}

/** "SRC>DEST,PATH:" of our frames for these settings, or null while the call, the destination or a digipeater is none. */
function header(values: Readonly<Record<string, string>>): string | null {
  const [call = ""] = callList(values["station/call"] ?? "");
  const [destination = ""] = callList(values["beacon/destination"] ?? "");
  const path = callList(values["beacon/path"] ?? "");
  return [call, destination, ...path].every(validCall) ? `${call}>${[destination, ...path].join(",")}:` : null;
}

/** DDHHMM and a z: the time of a status report, in UTC. */
function statusStamp(now: Date): string {
  const two = (n: number): string => String(n).padStart(2, "0");
  return `${two(now.getUTCDate())}${two(now.getUTCHours())}${two(now.getUTCMinutes())}z`;
}

/** The TNC2 text of the static status report, made at `now`; null while the status is empty, a radio makes the status instead (`status/rigctld`) or the settings make no frame. */
export function statusText(values: Readonly<Record<string, string>>, now: Date): string | null {
  const status = (values["station/status"] ?? "").trim();
  const head = header(values);
  return status === "" || (values["status/rigctld"] ?? "").trim() !== "" || head === null ? null : `${head}>${statusStamp(now)}${status}`;
}

/** The TNC2 text of the beacon for these settings (key to text, as the form holds them), or null when they do not make one: a call that is not a call, a position off the earth, a symbol that is none. */
export function beaconText(values: Readonly<Record<string, string>>): string | null {
  const head = header(values);
  const lat = number(values["station/lat"], -90, 90);
  const lon = number(values["station/lon"], -180, 180);
  const table = values["station/symbol_table"] ?? "";
  const code = values["station/symbol_code"] ?? "";
  if (head === null || lat === null || lon === null || !validSymbol(table, code)) return null;
  const extension = phg(values);
  if (extension === null) return null;
  const compressed = values["beacon/compressed"] === "true";
  const dao = !compressed && values["beacon/dao"] === "true";
  const position = compressed ? compressedPosition(lat, lon, table, code) : uncompressedPosition(lat, lon, table, code, dao);
  return `${head}=${position}${extension}${values["station/comment"] ?? ""}${dao ? daoText(lat, lon) : ""}`;
}
