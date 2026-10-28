// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { setup as source } from "@/i18n/en/setup";
import type { Message } from "@/i18n/message";

export const setup: Record<keyof typeof source, Message> = {
  "setup.title": "Configuração",
  "setup.step.call": "Indicativo",
  "setup.step.position": "Posição",
  "setup.step.symbol": "Símbolo",
  "setup.step.radio": "Rádio",
  "setup.step_label": "{n} {title}",
  "setup.done": "Concluído",
  "setup.close": "Fechar",
  "setup.back": "Voltar",
  "setup.next": "Avançar",
  "setup.saving": "Salvando...",
  "setup.finish": "Concluir",

  "setup.call.label": "Seu indicativo",
  "setup.port_automatic": "Automática",
  "setup.symbols": "Símbolos",
  "setup.symbol.house": "Casa",
  "setup.symbol.car": "Carro",
  "setup.symbol.truck": "Caminhão",
  "setup.symbol.van": "Van",
  "setup.symbol.motorcycle": "Moto",
  "setup.symbol.bike": "Bicicleta",
  "setup.symbol.walker": "A pé",
  "setup.symbol.boat": "Barco",
  "setup.symbol.digipeater": "Digipeater",
  "setup.symbol.weather_station": "Estação meteorológica",
  "setup.symbol.portable": "Portátil",
  "setup.symbol.antenna": "Antena",

  "setup.map_auto": "Baixando o mapa da sua região…",
  "setup.map_later": "O mapa detalhado será baixado quando você estiver online.",
};
