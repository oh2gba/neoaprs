// How long a time is, told in words: the unit of a length of time, and the sentences that put one in a place (lib/format.ts). {span} is one of the four units.
export const time = {
  "time.span.s": "{n} s",
  "time.span.min": "{n} min",
  "time.span.h": "{n} h",
  "time.span.d": "{n} d",
  "time.ago": "{span} ago",
  "time.in": "in {span}",
  "time.up": "up {span}",
  "time.now": "now",
  "time.nothing_heard": "nothing heard",
  "time.nothing_heard_since": "nothing heard since {time} ({span})",
} as const;
