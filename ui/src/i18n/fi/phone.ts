// The phone code of Settings, Web page.
import type { phone as en } from "@/i18n/en/phone";
import type { Message } from "@/i18n/message";

export const phone: Record<keyof typeof en, Message> = {
  "phone.code.label": "Avaa puhelimessa",
  "phone.code.tip_label": "Tietoa koodista",
  "phone.code.tip1": "Osoita koodia saman verkon puhelimen kameralla.",
  "phone.network.tip2": "Kytke se päälle: pääsyavain ja puhelimen koodi tulevat näkyviin.",
};
