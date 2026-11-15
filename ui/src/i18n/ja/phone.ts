// The phone code of Settings, Web page.
import type { phone as en } from "@/i18n/en/phone";
import type { Message } from "@/i18n/message";

export const phone: Record<keyof typeof en, Message> = {
  "phone.code.label": "スマートフォンで開く",
  "phone.code.tip_label": "コードについて",
  "phone.code.tip1": "同じネットワークのスマートフォンのカメラをコードに向けます。",
  "phone.network.tip2": "オンにすると、アクセスキーとスマートフォン用のコードが表示されます。",
};
