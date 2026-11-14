// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { map as source } from "@/i18n/en/map";
import type { Message } from "@/i18n/message";

export const map: Record<keyof typeof source, Message> = {
  "map.label": "Kaart met de stations",
  "map.zoom_in": "Inzoomen",
  "map.zoom_out": "Uitzoomen",
  "map.download": "Downloaden",
  "map.note.no_basemap": "Geen basiskaart",
  "map.note.no_detail": "Geen detailkaart",
  "map.note.no_engine": "De kaart kon niet worden geladen",
  "map.note.unreadable": "Het kaartbestand is onleesbaar",
  "map.follow_me": "Mijn positie volgen",
  "map.aloha": "ALOHA-cirkel: {km} km",

  "map.credits.hide": "Bronnen verbergen",
  "map.credits.show": "Bronnen van kaart en symbolen",
  "map.credits.symbols": "APRS-symbolen: de aprs.fi-set van Heikki Hannikainen, OH7LZB (github.com/hessu/aprs-symbols)",
  "map.credits.devices": "Apparaatnamen: de APRS-apparatenlijst van Hessu, OH7LZB (github.com/aprsorg/aprs-deviceid, CC BY-SA 2.0)",

  "map.menu_label": "Kaart",
  "map.menu.copy_position": "Positie {place} kopiëren",
  "map.menu.copy_locator": "Locator {locator} kopiëren",
  "map.menu.stats": "Statistieken",
  "map.menu.monitor": "Monitor",
  "map.menu.replay": "Terugspelen",
  "map.monitor.speed": "Snelheid",
  "map.monitor.speed_slow": "Langzaam",
  "map.monitor.speed_normal": "Normaal",
  "map.monitor.speed_fast": "Snel",

  "map.replay.label": "Terugspelen van de kaart",
  "map.replay.play": "Afspelen",
  "map.replay.pause": "Pauzeren",
  "map.replay.time": "Tijdstip",
  "map.replay.speed": "Snelheid",
  "map.replay.speed_n": "{n}×",
  "map.replay.span": "Periode",
  "map.replay.when_paused": "{what}: te wijzigen als je pauzeert",
  "map.replay.close": "Terugspelen sluiten",
  "map.replay.none": "Geen posities gehoord in de afgelopen {span}",

  "map.pick.tap": "Tik de plek aan op de kaart",
  "map.pick.cancel": "Annuleren",
};
