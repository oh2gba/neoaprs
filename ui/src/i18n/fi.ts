// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { Catalogue } from "@/i18n/catalogue";
import { beacon } from "@/i18n/fi/beacon";
import { bulletins } from "@/i18n/fi/bulletins";
import { email } from "@/i18n/fi/email";
import { errors } from "@/i18n/fi/errors";
import { help } from "@/i18n/fi/help";
import { map } from "@/i18n/fi/map";
import { stats } from "@/i18n/fi/stats";
import { messages } from "@/i18n/fi/messages";
import { nearby } from "@/i18n/fi/nearby";
import { objects } from "@/i18n/fi/objects";
import { packets } from "@/i18n/fi/packets";
import { settings } from "@/i18n/fi/settings";
import { setup } from "@/i18n/fi/setup";
import { shell } from "@/i18n/fi/shell";
import { stations } from "@/i18n/fi/stations";
import { symbols } from "@/i18n/fi/symbols";
import { time } from "@/i18n/fi/time";
import { weather } from "@/i18n/fi/weather";

export const fi: Catalogue = {
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
  ...stats,
  ...packets,
  ...weather,
  ...symbols,
  ...settings,
  ...beacon,
  ...setup,
  ...help,
};
