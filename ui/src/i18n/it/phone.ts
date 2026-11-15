// The phone code of Settings, Web page.
import type { phone as en } from "@/i18n/en/phone";
import type { Message } from "@/i18n/message";

export const phone: Record<keyof typeof en, Message> = {
  "phone.code.label": "Apri su un telefono",
  "phone.code.tip_label": "Informazioni sul codice",
  "phone.code.tip1": "Inquadralo con la fotocamera di un telefono sulla stessa rete.",
  "phone.network.tip2": "Attivalo: compaiono una chiave di accesso e un codice per un telefono.",
};
