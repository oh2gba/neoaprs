// The Maidenhead locator: 2 letters (A-R, fields of 20 x 10 degrees), 2 digits (squares of 2 x 1), 2 letters (a-x, subsquares of 5 x 2.5 minutes), and so on. The Location of a form (components/LocationField.vue) takes the
// centre of the square a locator names, and writes the locator of a position that was picked on the map or typed.
import { t } from "@/i18n";
import { onEarth, parseNumber } from "@/lib/fieldcheck";

const FIELD_LETTERS = 18; // A-R
const SUB_LETTERS = 24; // a-x
const LOCATOR = /^([A-R]{2})([0-9]{2})(?:([A-X]{2})(?:([0-9]{2}))?)?$/i;

function letter(char: string): number {
  return char.toUpperCase().charCodeAt(0) - 65;
}

/** Degrees rounded to 4 decimals (about 10 m, finer than a subsquare), as a number. */
function round(degrees: number): number {
  return Math.round(degrees * 10000) / 10000;
}

/** The centre of the square a locator of 4, 6 or 8 characters names; null for text that is no locator. */
export function locatorToPosition(text: string): { lat: number; lon: number } | null {
  const match = LOCATOR.exec(text.trim());
  if (!match) return null;
  const [, field = "", square = "", sub, extended] = match;
  let lon = -180 + letter(field[0] ?? "") * 20 + Number(square[0]) * 2;
  let lat = -90 + letter(field[1] ?? "") * 10 + Number(square[1]);
  let width = 2;
  let height = 1;
  if (sub) {
    width /= SUB_LETTERS;
    height /= SUB_LETTERS;
    lon += letter(sub[0] ?? "") * width;
    lat += letter(sub[1] ?? "") * height;
  }
  if (extended) {
    width /= 10;
    height /= 10;
    lon += Number(extended[0]) * width;
    lat += Number(extended[1]) * height;
  }
  return { lat: round(lat + height / 2), lon: round(lon + width / 2) };
}

/** The locator of 6 characters of a position (`KP20ie`): field and square in capitals, the subsquare in small letters. */
export function positionToLocator(lat: number, lon: number): string {
  if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180)) return "";
  const x = Math.min(lon + 180, 359.99999999);
  const y = Math.min(lat + 90, 179.99999999);
  const fieldX = Math.floor(x / 20);
  const fieldY = Math.floor(y / 10);
  const squareX = Math.floor((x - fieldX * 20) / 2);
  const squareY = Math.floor(y - fieldY * 10);
  const subX = Math.min(SUB_LETTERS - 1, Math.floor(((x - fieldX * 20 - squareX * 2) / 2) * SUB_LETTERS));
  const subY = Math.min(SUB_LETTERS - 1, Math.floor((y - fieldY * 10 - squareY) * SUB_LETTERS));
  const upper = (n: number) => String.fromCharCode(65 + n);
  const lower = (n: number) => String.fromCharCode(97 + n);
  return `${upper(Math.min(FIELD_LETTERS - 1, fieldX))}${upper(Math.min(FIELD_LETTERS - 1, fieldY))}${squareX}${squareY}${lower(subX)}${lower(subY)}`;
}

/** A place in words, as the Location lines say it: degrees with N or S, E or W, and the locator ("60.42945 N, 24.14524 E · KP20bk"). */
function placeLine(lat: number, lon: number): string {
  const shown = (value: number) => String(Math.round(Math.abs(value) * 1e5) / 1e5);
  return `${shown(lat)} ${lat < 0 ? "S" : "N"}, ${shown(lon)} ${lon < 0 ? "W" : "E"} · ${positionToLocator(lat, lon)}`;
}

/** The place the two texts of a form hold, in words (`placeLine`); null while they are no place (empty, not numbers, off the earth). */
export function placeOfText(lat: string, lon: string): string | null {
  const north = parseNumber(lat);
  const east = parseNumber(lon);
  return north !== null && east !== null && onEarth(north, east) ? placeLine(north, east) : null;
}

/** The locator of the two texts of a form, "" while they are no place. */
export function locatorOfText(lat: string, lon: string): string {
  const north = parseNumber(lat);
  const east = parseNumber(lon);
  return north !== null && east !== null && onEarth(north, east) ? positionToLocator(north, east) : "";
}

const LOCATOR_FROM = 6; // a locator of fewer characters is still being typed

/** What is wrong with a locator as it is typed: said once there are 6 characters and they are not a locator (7 is a locator of 8 on the way); "" otherwise. */
export function locatorProblem(text: string): string {
  const typed = text.trim();
  return typed.length >= LOCATOR_FROM && typed.length !== 7 && locatorToPosition(typed) === null ? t("settings.locator.invalid") : "";
}
