// Italian: this translation has not been reviewed by a native-speaking ham yet; corrections are welcome.
import type { Catalogue } from "@/i18n/catalogue";
import { beacon } from "@/i18n/it/beacon";
import { bulletins } from "@/i18n/it/bulletins";
import { email } from "@/i18n/it/email";
import { errors } from "@/i18n/it/errors";
import { help } from "@/i18n/it/help";
import { map } from "@/i18n/it/map";
import { stats } from "@/i18n/it/stats";
import { messages } from "@/i18n/it/messages";
import { nearby } from "@/i18n/it/nearby";
import { objects } from "@/i18n/it/objects";
import { packets } from "@/i18n/it/packets";
import { settings } from "@/i18n/it/settings";
import { setup } from "@/i18n/it/setup";
import { shell } from "@/i18n/it/shell";
import { stations } from "@/i18n/it/stations";
import { symbols } from "@/i18n/it/symbols";
import { time } from "@/i18n/it/time";
import { weather } from "@/i18n/it/weather";

export const it: Catalogue = {
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
