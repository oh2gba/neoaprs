import type { map as en } from "@/i18n/en/map";
import type { Message } from "@/i18n/message";

export const map: Readonly<Record<keyof typeof en, Message>> = {
  "map.label": "Mapa de las estaciones",
  "map.download": "Descargar",
  "map.note.no_basemap": "Sin mapa base",
  "map.note.no_detail": "Sin mapa detallado",
  "map.note.no_engine": "No se pudo cargar el mapa",

  "map.credits.hide": "Ocultar los créditos",
  "map.credits.show": "Créditos del mapa y los símbolos",
  "map.credits.symbols": "Símbolos APRS: juego de aprs.fi de Heikki Hannikainen, OH7LZB (github.com/hessu/aprs-symbols)",

  "map.pick.tap": "Toca el lugar en el mapa",
  "map.pick.cancel": "Cancelar",
};
