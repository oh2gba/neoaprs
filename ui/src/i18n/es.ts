// Spanish: this translation has not been reviewed by a native-speaking ham yet; corrections are welcome.
import type { Catalogue } from "@/i18n/catalogue";
import { beacon } from "@/i18n/es/beacon";
import { bulletins } from "@/i18n/es/bulletins";
import { email } from "@/i18n/es/email";
import { errors } from "@/i18n/es/errors";
import { help } from "@/i18n/es/help";
import { map } from "@/i18n/es/map";
import { messages } from "@/i18n/es/messages";
import { nearby } from "@/i18n/es/nearby";
import { objects } from "@/i18n/es/objects";
import { packets } from "@/i18n/es/packets";
import { settings } from "@/i18n/es/settings";
import { setup } from "@/i18n/es/setup";
import { shell } from "@/i18n/es/shell";
import { stations } from "@/i18n/es/stations";
import { symbols } from "@/i18n/es/symbols";
import { time } from "@/i18n/es/time";
import { weather } from "@/i18n/es/weather";

export const es: Catalogue = {
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
};
