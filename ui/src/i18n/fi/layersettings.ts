// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { layersettings as source } from "@/i18n/en/layersettings";
import type { Message } from "@/i18n/message";

export const layersettings: Record<keyof typeof source, Message> = {
  "layers.settings.none": "Ei mitään",
  "layers.settings.aircraft_tip_label": "Tietoa ilma-aluksista",
  "layers.settings.aircraft_tip1": "Mistä ilma-alukset tulevat: internetin palvelusta tai omasta vastaanottimesta.",
  "layers.settings.aircraft_tip2": "Ilma-alukset näkyvät kartalla, kun Ilma-alukset on valittu Tasot-ruudussa.",
  "layers.settings.ships_tip_label": "Tietoa aluksista",
  "layers.settings.ships_tip1":
    "Fintraffic kattaa Suomen vesialueet ja on valittavissa vain, kun karttasi yltää niille. Tai käytä omaa vastaanotinta.",
  "layers.settings.ships_tip2": "Alukset näkyvät kartalla, kun Alukset on valittu Tasot-ruudussa.",
  "layers.receiver.own": "Oma vastaanotin",
  "layers.receiver.address": "Vastaanottimen osoite",
  "layers.receiver.empty": "Tämä tietokone",
  "layers.receiver.radarcape_tip": "Radarcapesi osoite verkossasi.",
  "layers.receiver.aircraft_tip_label": "Tietoa vastaanottimen osoitteesta",
  "layers.receiver.aircraft_tip1":
    "Vastaanotin, jossa toimii readsb, dump1090, tar1090 tai PiAware, esimerkiksi Raspberry Pi:llä. Kirjoita sen nimi, numero tai verkko-osoite.",
  "layers.receiver.aircraft_tip2": "Jätä tyhjäksi, kun vastaanotin toimii tällä tietokoneella.",
  "layers.receiver.ships_tip_label": "Tietoa vastaanottimen osoitteesta",
  "layers.receiver.ships_tip1": "Sen tietokoneen nimi, joka lähettää vastaanottimesi alusviestit.",
  "layers.receiver.ships_tip2": "Jätä tyhjäksi, kun vastaanotin toimii tällä tietokoneella.",
  "layers.receiver.state.looking": "etsitään",
  "layers.receiver.state.receiving": "vastaanottaa",
  "layers.receiver.state.no_answer": "ei vastausta",
  "layers.receiver.line.looking": "Etsitään vastaanotinta",
  "layers.receiver.line.no_answer": "Vastaanotin ei vastaa",
  "layers.receiver.line.aircraft": {
    one: "Vastaanotetaan: {n} ilma-alus, {span} sitten",
    other: "Vastaanotetaan: {n} ilma-alusta, {span} sitten",
  },
  "layers.receiver.line.aircraft_none": "Vastaanotetaan, ei vielä ilma-aluksia",
  "layers.receiver.line.ships": {
    one: "Vastaanotetaan: {n} alus, {span} sitten",
    other: "Vastaanotetaan: {n} alusta, {span} sitten",
  },
  "layers.receiver.line.ships_none": "Yhteys on, ei vielä kuultu aluksia",
};
