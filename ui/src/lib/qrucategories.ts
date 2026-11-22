// The standard groups of local info (as asked for by APRSISCE/32 and YAAC), each with a plain name.
// An object's Category is one of them. The code goes on the air and other programs look for it, so
// it never changes; the label is a catalogue message keyed by the code. An own category is any
// other word of 1 to 8 letters and digits; a group not listed is shown as its code.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";

/** The standard groups in the order of the Category choice. */
export const CATEGORY_CODES = [
  "RP2M",
  "RP70",
  "RP6M",
  "RP10",
  "RP23",
  "RD2M",
  "RD70",
  "ECHO",
  "CLUB",
  "STOR",
  "FUEL",
  "FOOD",
  "SHOP",
  "POST",
  "HOSP",
  "AMBU",
  "POLI",
  "FIRE",
  "CIVD",
  "AIRP",
  "AERO",
  "HELI",
  "LIFEBOAT",
  "LTHS",
  "RAIL",
  "SRAIL",
  "VETE",
  "T2SRV",
  "WOTA",
] as const;

/** The message id of a standard group's plain name. */
export function categoryMessage(code: string): MessageId {
  return `objects.category.${code.toLowerCase()}` as MessageId;
}

/** Whether the code is one of the standard groups (any case). */
export function isStandardCategory(code: string): boolean {
  return (CATEGORY_CODES as readonly string[]).includes(code.trim().toUpperCase());
}

/** The plain name of a group, or the code itself if it is not a standard one. */
export function categoryLabel(code: string): string {
  return isStandardCategory(code) ? t(categoryMessage(code)) : code;
}

/** A group with its code when it has a plain name ("2 m repeater (RP2M)"); else the code. */
export function groupName(code: string): string {
  return isStandardCategory(code) ? `${categoryLabel(code)} (${code})` : code;
}
