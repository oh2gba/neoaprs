// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Over HF-tests",
  "skeds.about1":
    "Voor stations die APRS op HF uitproberen: zeg wanneer je in de lucht bent en op welke frequentie, zodat een ander station met je kan testen.",
  "skeds.about2": "Het bord staat openbaar op neo.oh2gba.eu. Het gaat niet via de radio.",

  "skeds.empty": "Geen tests gepland.",
  "skeds.past_title": "Afgelopen tests",
  "skeds.past_empty": "Geen afgelopen tests.",
  "skeds.when": "{from} tot {to} UTC",
  "skeds.local": "Jouw tijd: {from} tot {to}",
  "skeds.ours": "van ons",
  "skeds.join": "Aansluiten",
  "skeds.join_title": "Een eigen test plannen, om dezelfde tijd op dezelfde frequentie",
  "skeds.join_label": "Aansluiten bij de test van {calls}, {when}",
  "skeds.delete_title": "Verwijderen (van het bord halen)",
  "skeds.delete_label": "Onze test verwijderen, {when}",

  "skeds.post_label": "Test plannen",
  "skeds.day": "Dag",
  "skeds.time": "Tijd (UTC)",
  "skeds.from": "Begin",
  "skeds.to": "Einde",
  "skeds.until": "tot",
  "skeds.frequency": "Frequentie",
  "skeds.frequency_other": "Anders",
  "skeds.dial": "Afstemfrequentie",
  "skeds.note": "Opmerking",
  "skeds.post": "Op neo.oh2gba.eu plaatsen",
  "skeds.chat_title": "Chat",
  "skeds.chat_label": "Een regel voor de chat",
  "skeds.chat_send": "Verzenden",
  "skeds.chat_empty": "Nog niets gezegd.",
  "skeds.chat_closed": "De chat is gesloten.",
  "skeds.chat_popup": "Chat van de HF-tests: {call}",
  "skeds.chat_popup_more": {
    one: "Chat van de HF-tests: {n} nieuwe regel, van {call}",
    other: "Chat van de HF-tests: {n} nieuwe regels, de laatste van {call}",
  },
} as const;
