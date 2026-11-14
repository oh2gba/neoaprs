// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { time as source } from "@/i18n/en/time";
import type { Message } from "@/i18n/message";

export const time: Record<keyof typeof source, Message> = {
  "time.span.s": "{n} s",
  "time.span.min": "{n} min",
  "time.span.h": "{n} h",
  "time.span.d": "{n} d",
  "time.ago": "{span} geleden",
  "time.in": "over {span}",
  "time.now": "nu",
  "time.nothing_heard": "niets gehoord",
  "time.nothing_heard_since": "niets gehoord sinds {time} ({span})",
};
