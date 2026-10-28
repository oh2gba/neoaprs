// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { Catalogue } from "@/i18n/catalogue";
import { beacon } from "@/i18n/ja/beacon";
import { bulletins } from "@/i18n/ja/bulletins";
import { email } from "@/i18n/ja/email";
import { errors } from "@/i18n/ja/errors";
import { help } from "@/i18n/ja/help";
import { map } from "@/i18n/ja/map";
import { stats } from "@/i18n/ja/stats";
import { messages } from "@/i18n/ja/messages";
import { nearby } from "@/i18n/ja/nearby";
import { objects } from "@/i18n/ja/objects";
import { packets } from "@/i18n/ja/packets";
import { settings } from "@/i18n/ja/settings";
import { setup } from "@/i18n/ja/setup";
import { shell } from "@/i18n/ja/shell";
import { stations } from "@/i18n/ja/stations";
import { symbols } from "@/i18n/ja/symbols";
import { time } from "@/i18n/ja/time";
import { weather } from "@/i18n/ja/weather";

export const ja: Catalogue = {
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
