import type { layerbox as en } from "@/i18n/en/layerbox";
import type { Message } from "@/i18n/message";

export const layerbox: Readonly<Record<keyof typeof en, Message>> = {
  "layers.box.button": "Camadas",
  "layers.box.tracks": "Percursos",
  "layers.box.aloha": "Círculo ALOHA",
  "layers.box.grid": "Quadrícula locator",
  "layers.box.daynight": "Dia e noite",
};
