import type { time as en } from "@/i18n/en/time";
import type { Message } from "@/i18n/message";

export const time: Readonly<Record<keyof typeof en, Message>> = {
  "time.span.s": "{n} s",
  "time.span.min": "{n} min",
  "time.span.h": "{n} h",
  "time.span.d": "{n} g",
  "time.ago": "{span} fa",
  "time.in": "tra {span}",
  "time.now": "ora",
  "time.nothing_heard": "nulla ricevuto",
  "time.nothing_heard_since": "nulla ricevuto da {time} ({span})",
};
