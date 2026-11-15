// The phone code of Settings, Web page.
import type { phone as en } from "@/i18n/en/phone";
import type { Message } from "@/i18n/message";

export const phone: Record<keyof typeof en, Message> = {
  "phone.code.label": "Abrir em um celular",
  "phone.code.tip_label": "Sobre o código",
  "phone.code.tip1": "Aponte para ele a câmera de um celular na mesma rede.",
  "phone.network.tip2": "Ligue-a: aparecem uma chave de acesso e um código para o celular.",
};
