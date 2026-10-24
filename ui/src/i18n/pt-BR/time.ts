// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { time as source } from "@/i18n/en/time";
import type { Message } from "@/i18n/message";

export const time: Record<keyof typeof source, Message> = {
  "time.span.s": "{n} s",
  "time.span.min": "{n} min",
  "time.span.h": "{n} h",
  "time.span.d": "{n} d",
  "time.ago": "há {span}",
  "time.in": "em {span}",
  "time.now": "agora",
  "time.nothing_heard": "nada recebido",
  "time.nothing_heard_since": "nada recebido desde {time} ({span})",
};
