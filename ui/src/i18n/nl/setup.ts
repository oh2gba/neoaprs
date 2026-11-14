// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { setup as source } from "@/i18n/en/setup";
import type { Message } from "@/i18n/message";

export const setup: Record<keyof typeof source, Message> = {
  "setup.title": "Instellen",
  "setup.step.call": "Roepnaam",
  "setup.step.position": "Positie",
  "setup.step.symbol": "Symbool",
  "setup.step.radio": "Radio",
  "setup.step_label": "{n} {title}",
  "setup.done": "Klaar",
  "setup.close": "Sluiten",
  "setup.back": "Terug",
  "setup.next": "Volgende",
  "setup.saving": "Opslaan…",
  "setup.finish": "Voltooien",

  "setup.call.label": "Je roepnaam",
  "setup.port_automatic": "Automatisch",
  "setup.symbols": "Symbolen",
  "setup.symbol.house": "Huis",
  "setup.symbol.car": "Auto",
  "setup.symbol.truck": "Vrachtwagen",
  "setup.symbol.van": "Bestelwagen",
  "setup.symbol.motorcycle": "Motorfiets",
  "setup.symbol.bike": "Fiets",
  "setup.symbol.walker": "Wandelaar",
  "setup.symbol.boat": "Boot",
  "setup.symbol.digipeater": "Digipeater",
  "setup.symbol.weather_station": "Weerstation",
  "setup.symbol.portable": "Portabel",
  "setup.symbol.antenna": "Antenne",

  "setup.map_auto": "Kaart van je omgeving downloaden…",
  "setup.map_later": "De detailkaart wordt gedownload zodra je online bent.",
};
