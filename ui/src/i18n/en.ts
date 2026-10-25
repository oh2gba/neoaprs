// The English catalogue, the source of every other: an id and its message, in the files of ./en/ by area. The type `MessageId` (catalogue.ts) is made from it, so a catalogue of another language has the same ids or does
// not compile, and `t("id")` with an id that is not here does not either. A new area is a file in ./en/ and a line here.
import { beacon } from "@/i18n/en/beacon";
import { bulletins } from "@/i18n/en/bulletins";
import { email } from "@/i18n/en/email";
import { errors } from "@/i18n/en/errors";
import { help } from "@/i18n/en/help";
import { map } from "@/i18n/en/map";
import { messages } from "@/i18n/en/messages";
import { nearby } from "@/i18n/en/nearby";
import { objects } from "@/i18n/en/objects";
import { packets } from "@/i18n/en/packets";
import { settings } from "@/i18n/en/settings";
import { setup } from "@/i18n/en/setup";
import { shell } from "@/i18n/en/shell";
import { stations } from "@/i18n/en/stations";
import { symbols } from "@/i18n/en/symbols";
import { time } from "@/i18n/en/time";
import { weather } from "@/i18n/en/weather";
import type { Message } from "@/i18n/message";

export const en = {
  ...shell,
  ...time,
  ...errors,
  ...messages,
  ...email,
  ...bulletins,
  ...objects,
  ...stations,
  ...nearby,
  ...map,
  ...packets,
  ...weather,
  ...symbols,
  ...settings,
  ...beacon,
  ...setup,
  ...help,
} as const satisfies Record<string, Message>;
