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
import { skeds } from "@/i18n/en/skeds";
import { stats } from "@/i18n/en/stats";
import { stations } from "@/i18n/en/stations";
import { symbols } from "@/i18n/en/symbols";
import { time } from "@/i18n/en/time";
import { u4 } from "@/i18n/en/u4";
import { u5a } from "@/i18n/en/u5a";
import { u5b } from "@/i18n/en/u5b";
import { u5c } from "@/i18n/en/u5c";
import { u6 } from "@/i18n/en/u6";
import { u2 } from "@/i18n/en/u2";
import { u3 } from "@/i18n/en/u3";
import { weather } from "@/i18n/en/weather";
import type { Message } from "@/i18n/message";

export const en = {
  ...shell,
  ...time,
  ...errors,
  ...messages,
  ...email,
  ...bulletins,
  ...skeds,
  ...objects,
  ...stations,
  ...nearby,
  ...map,
  ...stats,
  ...packets,
  ...weather,
  ...symbols,
  ...settings,
  ...beacon,
  ...setup,
  ...help,
  ...u4,
  ...u5a,
  ...u5b,
  ...u5c,
  ...u6,
  ...u2,
  ...u3,
} as const satisfies Record<string, Message>;
