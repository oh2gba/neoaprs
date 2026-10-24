// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { map as source } from "@/i18n/en/map";
import type { Message } from "@/i18n/message";

export const map: Record<keyof typeof source, Message> = {
  "map.label": "Mapa das estações",
  "map.zoom_in": "Aumentar o zoom",
  "map.zoom_out": "Diminuir o zoom",
  "map.download": "Baixar",
  "map.note.no_basemap": "Sem mapa base",
  "map.note.no_detail": "Sem mapa detalhado",
  "map.note.no_engine": "Não foi possível carregar o mapa",
  "map.aloha": "Círculo ALOHA: {km} km",

  "map.credits.hide": "Ocultar os créditos",
  "map.credits.show": "Créditos do mapa e dos símbolos",
  "map.credits.symbols": "Símbolos APRS: conjunto aprs.fi de Heikki Hannikainen, OH7LZB (github.com/hessu/aprs-symbols)",

  "map.pick.tap": "Toque no lugar do mapa",
  "map.pick.cancel": "Cancelar",
};
