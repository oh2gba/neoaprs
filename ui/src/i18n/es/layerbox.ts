import type { layerbox as en } from "@/i18n/en/layerbox";
import type { Message } from "@/i18n/message";

export const layerbox: Readonly<Record<keyof typeof en, Message>> = {
  "layers.box.button": "Capas",
  "layers.box.tracks": "Recorridos",
  "layers.box.aloha": "Círculo ALOHA",
  "layers.box.grid": "Cuadrícula de locators",
  "layers.box.daynight": "Día y noche",
  "layers.box.satellites": "Satélites",
};
