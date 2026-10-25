// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { Catalogue } from "@/i18n/catalogue";
import { beacon } from "@/i18n/pt-BR/beacon";
import { bulletins } from "@/i18n/pt-BR/bulletins";
import { email } from "@/i18n/pt-BR/email";
import { errors } from "@/i18n/pt-BR/errors";
import { help } from "@/i18n/pt-BR/help";
import { map } from "@/i18n/pt-BR/map";
import { messages } from "@/i18n/pt-BR/messages";
import { nearby } from "@/i18n/pt-BR/nearby";
import { objects } from "@/i18n/pt-BR/objects";
import { packets } from "@/i18n/pt-BR/packets";
import { settings } from "@/i18n/pt-BR/settings";
import { setup } from "@/i18n/pt-BR/setup";
import { shell } from "@/i18n/pt-BR/shell";
import { stations } from "@/i18n/pt-BR/stations";
import { symbols } from "@/i18n/pt-BR/symbols";
import { time } from "@/i18n/pt-BR/time";
import { weather } from "@/i18n/pt-BR/weather";

export const ptBR: Catalogue = {
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
