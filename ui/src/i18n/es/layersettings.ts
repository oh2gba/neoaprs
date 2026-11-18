import type { layersettings as en } from "@/i18n/en/layersettings";
import type { Message } from "@/i18n/message";

export const layersettings: Readonly<Record<keyof typeof en, Message>> = {
  "layers.settings.none": "Ninguno",
  "layers.settings.aircraft_tip_label": "Acerca de los aviones",
  "layers.settings.aircraft_tip1": "De dónde vienen los aviones: un servicio de internet, o un receptor propio.",
  "layers.settings.aircraft_tip2": "Los aviones salen en el mapa cuando Aviones está marcado en el cuadro Capas.",
  "layers.settings.ships_tip_label": "Acerca de los barcos",
  "layers.settings.ships_tip1": "Fintraffic cubre las aguas de Finlandia y solo aparece donde tu mapa llega a ellas. O usa un receptor propio.",
  "layers.settings.ships_tip2": "Los barcos salen en el mapa cuando Barcos está marcado en el cuadro Capas.",
  "layers.receiver.own": "Mi propio receptor",
  "layers.receiver.address": "Dirección del receptor",
  "layers.receiver.empty": "Este ordenador",
  "layers.receiver.radarcape_tip": "La dirección de tu Radarcape en tu red.",
  "layers.receiver.aircraft_tip_label": "Acerca de la dirección del receptor",
  "layers.receiver.aircraft_tip1":
    "Un receptor con readsb, dump1090, tar1090 o PiAware, por ejemplo en una Raspberry Pi. Escribe su nombre, su número o su dirección web.",
  "layers.receiver.aircraft_tip2": "Déjala vacía cuando el receptor funciona en este ordenador.",
  "layers.receiver.ships_tip_label": "Acerca de la dirección del receptor",
  "layers.receiver.ships_tip1": "El nombre del ordenador que envía los mensajes de barcos de tu receptor.",
  "layers.receiver.ships_tip2": "Déjala vacía cuando el receptor funciona en este ordenador.",
  "layers.receiver.state.looking": "buscando",
  "layers.receiver.state.receiving": "recibiendo",
  "layers.receiver.state.no_answer": "sin respuesta",
  "layers.receiver.line.looking": "Buscando el receptor",
  "layers.receiver.line.no_answer": "Sin respuesta del receptor",
  "layers.receiver.line.aircraft": { one: "Recibiendo: {n} avión, hace {span}", other: "Recibiendo: {n} aviones, hace {span}" },
  "layers.receiver.line.aircraft_none": "Recibiendo, aún sin aviones",
  "layers.receiver.line.ships": { one: "Recibiendo: {n} barco, hace {span}", other: "Recibiendo: {n} barcos, hace {span}" },
  "layers.receiver.line.ships_none": "Conectado, aún no se oye ningún barco",
};
