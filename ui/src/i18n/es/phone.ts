// The phone code of Settings, Web page.
import type { phone as en } from "@/i18n/en/phone";
import type { Message } from "@/i18n/message";

export const phone: Record<keyof typeof en, Message> = {
  "phone.code.label": "Abrir en un teléfono",
  "phone.code.tip_label": "Acerca del código",
  "phone.code.tip1": "Apunta hacia él la cámara de un teléfono de la misma red.",
  "phone.network.tip2": "Actívalo: aparecen una clave de acceso y un código para un teléfono.",
};
