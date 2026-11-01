// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { setup as source } from "@/i18n/en/setup";
import type { Message } from "@/i18n/message";

export const setup: Record<keyof typeof source, Message> = {
  "setup.title": "Käyttöönotto",
  "setup.step.call": "Kutsu",
  "setup.step.position": "Sijainti",
  "setup.step.symbol": "Symboli",
  "setup.step.radio": "Radio",
  "setup.step_label": "{n} {title}",
  "setup.done": "Valmis",
  "setup.close": "Sulje",
  "setup.back": "Takaisin",
  "setup.next": "Seuraava",
  "setup.saving": "Tallennetaan...",
  "setup.finish": "Valmis",

  "setup.call.label": "Kutsusi",
  "setup.port_automatic": "Automaattinen",
  "setup.symbols": "Symbolit",
  "setup.symbol.house": "Talo",
  "setup.symbol.car": "Auto",
  "setup.symbol.truck": "Kuorma-auto",
  "setup.symbol.van": "Pakettiauto",
  "setup.symbol.motorcycle": "Moottoripyörä",
  "setup.symbol.bike": "Polkupyörä",
  "setup.symbol.walker": "Jalankulkija",
  "setup.symbol.boat": "Vene",
  "setup.symbol.digipeater": "Digipeateri",
  "setup.symbol.weather_station": "Sääasema",
  "setup.symbol.portable": "Siirrettävä",
  "setup.symbol.antenna": "Antenni",

  "setup.map_auto": "Ladataan alueesi karttaa…",
  "setup.map_later": "Tarkka kartta ladataan, kun olet verkossa.",
};
