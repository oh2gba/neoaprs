import type { map as en } from "@/i18n/en/map";
import type { Message } from "@/i18n/message";

export const map: Readonly<Record<keyof typeof en, Message>> = {
  "map.label": "Mappa delle stazioni",
  "map.zoom_in": "Ingrandisci",
  "map.zoom_out": "Riduci",
  "map.download": "Scarica",
  "map.note.no_basemap": "Nessuna mappa di base",
  "map.note.no_detail": "Nessuna mappa dettagliata",
  "map.note.no_engine": "Impossibile caricare la mappa",
  "map.aloha": "Cerchio ALOHA: {km} km",

  "map.credits.hide": "Nascondi i crediti",
  "map.credits.show": "Crediti di mappa e simboli",
  "map.credits.symbols": "Simboli APRS: set aprs.fi di Heikki Hannikainen, OH7LZB (github.com/hessu/aprs-symbols)",

  "map.pick.tap": "Tocca il punto sulla mappa",
  "map.pick.cancel": "Annulla",
};
