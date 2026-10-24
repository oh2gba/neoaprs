// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { time as source } from "@/i18n/en/time";
import type { Message } from "@/i18n/message";

export const time: Record<keyof typeof source, Message> = {
  "time.span.s": "{n}秒",
  "time.span.min": "{n}分",
  "time.span.h": "{n}時間",
  "time.span.d": "{n}日",
  "time.ago": "{span}前",
  "time.in": "{span}後",
  "time.now": "今",
  "time.nothing_heard": "受信なし",
  "time.nothing_heard_since": "{time}から受信なし({span})",
};
