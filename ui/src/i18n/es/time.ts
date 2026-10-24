import type { time as en } from "@/i18n/en/time";
import type { Message } from "@/i18n/message";

export const time: Readonly<Record<keyof typeof en, Message>> = {
  "time.span.s": "{n} s",
  "time.span.min": "{n} min",
  "time.span.h": "{n} h",
  "time.span.d": "{n} d",
  "time.ago": "hace {span}",
  "time.in": "en {span}",
  "time.now": "ahora",
  "time.nothing_heard": "nada escuchado",
  "time.nothing_heard_since": "nada escuchado desde {time} ({span})",
};
