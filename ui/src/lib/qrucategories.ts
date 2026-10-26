// The standard groups of local info (the ones APRSISCE/32 and YAAC ask for), each with its plain name: an object's Category is one of them, and a server's groups are shown by them. The code is what goes on the air and what the other programs
// look for, so it is never changed; the label is a message of the catalogue, asked for by the code. An own category is any other word of 1 to 8 letters and digits ("Other...", in the Objects form), and a group that is not here is shown as its code.
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

/** The message of the plain name of a standard group. */
export function categoryMessage(code: string): MessageId {
  return `objects.category.${code.toLowerCase()}` as MessageId;
}

/** Whether the code is one of the standard groups (any case). */
export function isStandardCategory(code: string): boolean {
  return (CATEGORY_CODES as readonly string[]).includes(code.trim().toUpperCase());
}

/** The plain name of a group, or the code itself when it is not a standard one. */
export function categoryLabel(code: string): string {
  return isStandardCategory(code) ? t(categoryMessage(code)) : code;
}

/** A group in words, with its code when it has a plain name (the hover text of a tag): "2 m repeater (RP2M)"; any other code is itself. */
export function groupName(code: string): string {
  return isStandardCategory(code) ? `${categoryLabel(code)} (${code})` : code;
}
