// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { map as source } from "@/i18n/en/map";
import type { Message } from "@/i18n/message";

export const map: Record<keyof typeof source, Message> = {
  "map.label": "Asemien kartta",
  "map.zoom_in": "Lähennä",
  "map.zoom_out": "Loitonna",
  "map.download": "Lataa",
  "map.note.no_basemap": "Ei pohjakarttaa",
  "map.note.no_detail": "Ei tarkkaa karttaa",
  "map.note.no_engine": "Karttaa ei voitu ladata",
  "map.note.unreadable": "Karttatiedostoa ei voi lukea",
  "map.follow_me": "Seuraa sijaintiani",
  "map.aloha": "ALOHA-ympyrä: {km} km",

  "map.credits.hide": "Piilota tekijätiedot",
  "map.credits.show": "Kartan ja symbolien tekijätiedot",
  "map.credits.symbols": "APRS-symbolit: Heikki Hannikaisen, OH7LZB, aprs.fi-sarja (github.com/hessu/aprs-symbols)",
  "map.credits.devices": "Laitenimet: Hessun, OH7LZB, APRS-laitetunnisteluettelo (github.com/aprsorg/aprs-deviceid, CC BY-SA 2.0)",

  "map.menu_label": "Kartta",
  "map.menu.copy_position": "Kopioi sijainti {place}",
  "map.menu.copy_locator": "Kopioi lokaattori {locator}",
  "map.menu.stats": "Tilastot",
  "map.menu.monitor": "Monitori",
  "map.menu.replay": "Uusinta",

  "map.replay.label": "Kartan uusinta",
  "map.replay.play": "Toista",
  "map.replay.pause": "Tauko",
  "map.replay.time": "Uusinnan aika",
  "map.replay.speed": "Nopeus",
  "map.replay.speed_n": "{n}×",
  "map.replay.span": "Jakso",
  "map.replay.when_paused": "{what}: voi muuttaa tauon aikana",
  "map.replay.close": "Sulje uusinta",
  "map.replay.none": "Viimeisen ajanjakson ({span}) aikana ei kuultu sijainteja",

  "map.pick.tap": "Napauta paikkaa kartalla",
  "map.pick.cancel": "Peruuta",
};
