// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Over skeds",
  "skeds.about1": "Met een sked laat je weten wanneer en op welke frequentie je in de lucht bent, zodat een ander station je daar kan vinden.",
  "skeds.about2": "Het bord staat openbaar op neo.oh2gba.eu. Het gaat niet via de radio.",

  "skeds.empty": "Geen komende skeds.",
  "skeds.when": "{from} tot {to} UTC",
  "skeds.local": "Jouw tijd: {from} tot {to}",
  "skeds.ours": "van ons",
  "skeds.join": "Aansluiten",
  "skeds.join_title": "Een eigen sked plaatsen, om dezelfde tijd op dezelfde frequentie",
  "skeds.join_label": "Aansluiten bij de sked van {calls}, {when}",
  "skeds.delete_title": "Verwijderen (van het bord halen)",
  "skeds.delete_label": "Onze sked verwijderen, {when}",

  "skeds.post_label": "Sked plaatsen",
  "skeds.day": "Dag",
  "skeds.time": "Tijd (UTC)",
  "skeds.from": "Begin",
  "skeds.to": "Einde",
  "skeds.until": "tot",
  "skeds.frequency": "Frequentie",
  "skeds.frequency_other": "Anders",
  "skeds.dial": "Dial",
  "skeds.note": "Opmerking",
  "skeds.post": "Op neo.oh2gba.eu plaatsen",
} as const;
