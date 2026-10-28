import type { setup as en } from "@/i18n/en/setup";
import type { Message } from "@/i18n/message";

export const setup: Readonly<Record<keyof typeof en, Message>> = {
  "setup.title": "Configurazione guidata",
  "setup.step.call": "Nominativo",
  "setup.step.position": "Posizione",
  "setup.step.symbol": "Simbolo",
  "setup.step.radio": "Radio",
  "setup.step_label": "{n} {title}",
  "setup.done": "Fatto",
  "setup.close": "Chiudi",
  "setup.back": "Indietro",
  "setup.next": "Avanti",
  "setup.saving": "Salvataggio...",
  "setup.finish": "Fine",

  "setup.call.label": "Il tuo nominativo",
  "setup.port_automatic": "Automatica",
  "setup.symbols": "Simboli",
  "setup.symbol.house": "Casa",
  "setup.symbol.car": "Auto",
  "setup.symbol.truck": "Camion",
  "setup.symbol.van": "Furgone",
  "setup.symbol.motorcycle": "Moto",
  "setup.symbol.bike": "Bici",
  "setup.symbol.walker": "Pedone",
  "setup.symbol.boat": "Barca",
  "setup.symbol.digipeater": "Digipeater",
  "setup.symbol.weather_station": "Stazione meteo",
  "setup.symbol.portable": "Portatile",
  "setup.symbol.antenna": "Antenna",

  "setup.map_auto": "Download della mappa della tua zona…",
  "setup.map_later": "La mappa dettagliata verrà scaricata quando sarai online.",
};
