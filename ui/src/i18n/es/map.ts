import type { map as en } from "@/i18n/en/map";
import type { Message } from "@/i18n/message";

export const map: Readonly<Record<keyof typeof en, Message>> = {
  "map.label": "Mapa de las estaciones",
  "map.zoom_in": "Acercar",
  "map.zoom_out": "Alejar",
  "map.download": "Descargar",
  "map.note.no_basemap": "Sin mapa base",
  "map.note.no_detail": "Sin mapa detallado",
  "map.note.no_engine": "No se pudo cargar el mapa",
  "map.note.unreadable": "No se puede leer el archivo del mapa",
  "map.follow_me": "Seguir mi posición",
  "map.aloha": "Círculo ALOHA: {km} km",

  "map.credits.hide": "Ocultar los créditos",
  "map.credits.show": "Créditos del mapa y los símbolos",
  "map.credits.symbols": "Símbolos APRS: juego de aprs.fi de Heikki Hannikainen, OH7LZB (github.com/hessu/aprs-symbols)",
  "map.credits.devices": "Nombres de dispositivos: lista de identificación APRS de Hessu, OH7LZB (github.com/aprsorg/aprs-deviceid, CC BY-SA 2.0)",

  "map.menu_label": "Mapa",
  "map.menu.copy_position": "Copiar la posición {place}",
  "map.menu.copy_locator": "Copiar el locator {locator}",
  "map.menu.stats": "Estadísticas",
  "map.pick.tap": "Toca el lugar en el mapa",
  "map.pick.cancel": "Cancelar",
};
