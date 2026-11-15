// The phone code of Settings, Web page.
import type { phone as en } from "@/i18n/en/phone";
import type { Message } from "@/i18n/message";

export const phone: Record<keyof typeof en, Message> = {
  "phone.code.label": "Open op een telefoon",
  "phone.code.tip_label": "Over de code",
  "phone.code.tip1": "Richt de camera van een telefoon die op hetzelfde netwerk zit erop.",
  "phone.network.tip2": "Zet het aan: er verschijnen een toegangssleutel en een code voor een telefoon.",
};
