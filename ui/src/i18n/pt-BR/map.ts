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
  "map.note.unreadable": "Não foi possível ler o arquivo do mapa",
  "map.follow_me": "Seguir minha posição",
  "map.aloha": "Círculo ALOHA: {km} km",

  "map.credits.hide": "Ocultar os créditos",
  "map.credits.show": "Créditos do mapa e dos símbolos",
  "map.credits.symbols": "Símbolos APRS: conjunto aprs.fi de Heikki Hannikainen, OH7LZB (github.com/hessu/aprs-symbols)",
  "map.credits.devices": "Nomes de dispositivos: lista de identificação APRS de Hessu, OH7LZB (github.com/aprsorg/aprs-deviceid, CC BY-SA 2.0)",

  "map.menu_label": "Mapa",
  "map.menu.copy_position": "Copiar a posição {place}",
  "map.menu.copy_locator": "Copiar o locator {locator}",
  "map.menu.stats": "Estatísticas",
  "map.menu.replay": "Reproduzir",
  "map.replay.label": "Reprodução do mapa",
  "map.replay.play": "Reproduzir",
  "map.replay.pause": "Pausar",
  "map.replay.time": "Hora da reprodução",
  "map.replay.speed": "Velocidade",
  "map.replay.speed_n": "{n}×",
  "map.replay.span": "Período",
  "map.replay.when_paused": "{what}: pode ser alterado com a reprodução pausada",
  "map.replay.close": "Fechar a reprodução",
  "map.replay.none": "Nenhuma posição ouvida no período escolhido ({span})",
  "map.pick.tap": "Toque no lugar do mapa",
  "map.pick.cancel": "Cancelar",
};
