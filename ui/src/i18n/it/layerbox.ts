import type { layerbox as en } from "@/i18n/en/layerbox";
import type { Message } from "@/i18n/message";

export const layerbox: Readonly<Record<keyof typeof en, Message>> = {
  "layers.box.button": "Livelli",
  "layers.box.tracks": "Tracce",
  "layers.box.aloha": "Cerchio ALOHA",
  "layers.box.grid": "Griglia locator",
  "layers.box.daynight": "Giorno e notte",
  "layers.box.satellites": "Satelliti",
};
