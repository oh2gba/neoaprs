// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { layersettings as source } from "@/i18n/en/layersettings";
import type { Message } from "@/i18n/message";

export const layersettings: Record<keyof typeof source, Message> = {
  "layers.settings.none": "Geen",
  "layers.settings.source": "Bron",
  "layers.settings.aircraft_tip_label": "Over vliegtuigen",
  "layers.settings.aircraft_tip1": "Waar de vliegtuigen vandaan komen: een dienst op internet, of een eigen ontvanger.",
  "layers.settings.aircraft_tip2": "Vliegtuigen staan op de kaart als Vliegtuigen is aangevinkt in het vak Lagen.",
  "layers.settings.ships_tip_label": "Over schepen",
  "layers.settings.ships_tip1":
    "Fintraffic dekt de wateren van Finland en staat er alleen bij waar je kaart die bereikt. Of gebruik een eigen ontvanger.",
  "layers.settings.ships_tip2": "Schepen staan op de kaart als Schepen is aangevinkt in het vak Lagen.",
  "layers.receiver.own": "Mijn eigen ontvanger",
  "layers.receiver.address": "Adres van de ontvanger",
  "layers.receiver.empty": "Deze computer",
  "layers.receiver.radarcape_tip": "Het adres van je Radarcape op je netwerk.",
  "layers.receiver.aircraft_tip_label": "Over het adres van de ontvanger",
  "layers.receiver.aircraft_tip1":
    "Een ontvanger met readsb, dump1090, tar1090 of PiAware, bijvoorbeeld op een Raspberry Pi. Typ de naam, het nummer of het webadres.",
  "layers.receiver.aircraft_tip2": "Laat het leeg als de ontvanger op deze computer draait.",
  "layers.receiver.ships_tip_label": "Over het adres van de ontvanger",
  "layers.receiver.ships_tip1": "De naam van de computer die de scheepsberichten van je ontvanger verstuurt.",
  "layers.receiver.ships_tip2": "Laat het leeg als de ontvanger op deze computer draait.",
  "layers.aisstream.key": "Sleutel",
  "layers.aisstream.get_key": "Sleutel aanvragen",
  "layers.aisstream.key_tip_label": "Over de sleutel",
  "layers.aisstream.key_tip": "De sleutel is van jezelf, en AISStream geeft hem gratis.",
  "layers.aisstream.refused": "AISStream heeft deze sleutel niet geaccepteerd.",
  "layers.receiver.state.looking": "zoeken",
  "layers.receiver.state.receiving": "ontvangt",
  "layers.receiver.state.no_answer": "geen antwoord",
  "layers.receiver.line.looking": "De ontvanger zoeken",
  "layers.receiver.line.no_answer": "Geen antwoord van de ontvanger",
  "layers.receiver.state.no_ais": "geen AIS",
  "layers.receiver.line.no_ais": "Verbonden, maar er komt geen AIS van",
  "layers.receiver.line.aircraft": {
    one: "Ontvangt: {n} vliegtuig, {span} geleden",
    other: "Ontvangt: {n} vliegtuigen, {span} geleden",
  },
  "layers.receiver.line.aircraft_none": "Ontvangt, nog geen vliegtuig",
  "layers.receiver.line.ships": {
    one: "Ontvangt: {n} schip, {span} geleden",
    other: "Ontvangt: {n} schepen, {span} geleden",
  },
  "layers.receiver.line.ships_none": "Verbonden, nog geen schip gehoord",
};
