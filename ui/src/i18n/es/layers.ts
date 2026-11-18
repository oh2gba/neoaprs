import type { layers as en } from "@/i18n/en/layers";
import type { Message } from "@/i18n/message";

export const layers: Readonly<Record<keyof typeof en, Message>> = {
  "layers.aircraft": "Aviones",
  "layers.ships": "Barcos",
};
