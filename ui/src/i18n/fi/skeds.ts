// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Tietoa skedeistä",
  "skeds.about1": "Skedi kertoo, milloin olet äänessä ja millä taajuudella, jotta toinen asema voi tavata sinut siellä.",
  "skeds.about2": "Taulu on julkinen, osoitteessa neo.oh2gba.eu. Sitä ei lähetetä radiolla.",

  "skeds.empty": "Ei tulevia skedejä.",
  "skeds.when": "{from} – {to} UTC",
  "skeds.local": "Paikallinen aikasi: {from} – {to}",
  "skeds.ours": "omamme",
  "skeds.join": "Liity",
  "skeds.join_title": "Lisää oma skedi samaan aikaan samalle taajuudelle",
  "skeds.join_label": "Liity skediin: {calls}, {when}",
  "skeds.delete_title": "Poista (ota pois taululta)",
  "skeds.delete_label": "Poista oma skedimme, {when}",

  "skeds.post_label": "Lisää skedi",
  "skeds.day": "Päivä",
  "skeds.time": "Aika (UTC)",
  "skeds.from": "Alkaa",
  "skeds.to": "Päättyy",
  "skeds.until": "–",
  "skeds.frequency": "Taajuus",
  "skeds.frequency_other": "Muu",
  "skeds.dial": "Dial",
  "skeds.note": "Huomautus",
  "skeds.post": "Julkaise osoitteessa neo.oh2gba.eu",
} as const;
