import type { setup as en } from "@/i18n/en/setup";
import type { Message } from "@/i18n/message";

export const setup: Readonly<Record<keyof typeof en, Message>> = {
  "setup.title": "Configuración inicial",
  "setup.step.call": "Indicativo",
  "setup.step.position": "Posición",
  "setup.step.symbol": "Símbolo",
  "setup.step.radio": "Radio",
  "setup.step_label": "{n} {title}",
  "setup.done": "Hecho",
  "setup.close": "Cerrar",
  "setup.back": "Atrás",
  "setup.next": "Siguiente",
  "setup.saving": "Guardando...",
  "setup.finish": "Terminar",

  "setup.call.label": "Tu indicativo",
  "setup.port_automatic": "Automático",
  "setup.symbols": "Símbolos",
  "setup.symbol.house": "Casa",
  "setup.symbol.car": "Coche",
  "setup.symbol.truck": "Camión",
  "setup.symbol.van": "Furgoneta",
  "setup.symbol.motorcycle": "Moto",
  "setup.symbol.bike": "Bici",
  "setup.symbol.walker": "Peatón",
  "setup.symbol.boat": "Barco",
  "setup.symbol.digipeater": "Digipeater",
  "setup.symbol.weather_station": "Estación meteorológica",
  "setup.symbol.portable": "Portátil",
  "setup.symbol.antenna": "Antena",

  "setup.map_auto": "Descargando el mapa de tu zona…",
  "setup.map_later": "El mapa detallado se descargará cuando tengas conexión.",
};
