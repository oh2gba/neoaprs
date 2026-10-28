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
  "map.note.unreadable": "Impossibile leggere il file della mappa",
  "map.follow_me": "Segui la mia posizione",
  "map.aloha": "Cerchio ALOHA: {km} km",

  "map.credits.hide": "Nascondi i crediti",
  "map.credits.show": "Crediti di mappa e simboli",
  "map.credits.symbols": "Simboli APRS: set aprs.fi di Heikki Hannikainen, OH7LZB (github.com/hessu/aprs-symbols)",
  "map.credits.devices": "Nomi dei dispositivi: elenco di identificazione APRS di Hessu, OH7LZB (github.com/aprsorg/aprs-deviceid, CC BY-SA 2.0)",

  "map.menu_label": "Mappa",
  "map.menu.copy_position": "Copia la posizione {place}",
  "map.menu.copy_locator": "Copia il locator {locator}",
  "map.menu.stats": "Statistiche",
  "map.menu.replay": "Riproduci",
  "map.replay.label": "Riproduzione della mappa",
  "map.replay.play": "Riproduci",
  "map.replay.pause": "Pausa",
  "map.replay.time": "Ora della riproduzione",
  "map.replay.speed": "Velocità",
  "map.replay.speed_n": "{n}×",
  "map.replay.span": "Periodo",
  "map.replay.when_paused": "{what}: si può cambiare in pausa",
  "map.replay.close": "Chiudi la riproduzione",
  "map.replay.none": "Nessuna posizione ricevuta nel periodo scelto ({span})",
  "map.pick.tap": "Tocca il punto sulla mappa",
  "map.pick.cancel": "Annulla",
};
