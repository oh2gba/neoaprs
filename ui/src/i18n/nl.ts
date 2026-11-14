// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { Catalogue } from "@/i18n/catalogue";
import { beacon } from "@/i18n/nl/beacon";
import { bulletins } from "@/i18n/nl/bulletins";
import { email } from "@/i18n/nl/email";
import { errors } from "@/i18n/nl/errors";
import { help } from "@/i18n/nl/help";
import { map } from "@/i18n/nl/map";
import { stats } from "@/i18n/nl/stats";
import { messages } from "@/i18n/nl/messages";
import { nearby } from "@/i18n/nl/nearby";
import { objects } from "@/i18n/nl/objects";
import { packets } from "@/i18n/nl/packets";
import { settings } from "@/i18n/nl/settings";
import { setup } from "@/i18n/nl/setup";
import { shell } from "@/i18n/nl/shell";
import { skeds } from "@/i18n/nl/skeds";
import { stations } from "@/i18n/nl/stations";
import { symbols } from "@/i18n/nl/symbols";
import { time } from "@/i18n/nl/time";
import { weather } from "@/i18n/nl/weather";

export const nl: Catalogue = {
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
};
