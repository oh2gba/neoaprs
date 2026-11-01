// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { time as source } from "@/i18n/en/time";
import type { Message } from "@/i18n/message";

export const time: Record<keyof typeof source, Message> = {
  "time.span.s": "{n} s",
  "time.span.min": "{n} min",
  "time.span.h": "{n} h",
  "time.span.d": "{n} pv",
  "time.ago": "{span} sitten",
  "time.in": "{span} kuluttua",
  "time.now": "nyt",
  "time.nothing_heard": "ei kuultu mitään",
  "time.nothing_heard_since": "ei kuultu mitään {time} jälkeen ({span})",
};
