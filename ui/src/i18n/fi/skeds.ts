// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Tietoa HF-testeistä",
  "skeds.about1":
    "Kun kokeilet APRS:ää HF:llä, kerro, milloin olet äänessä ja millä taajuudella, niin toinen asema voi testata kanssasi.",
  "skeds.about2": "Taulu on julkinen, osoitteessa neo.oh2gba.eu. Sitä ei lähetetä radiolla.",

  "skeds.empty": "Ei suunniteltuja testejä.",
  "skeds.past_title": "Menneet testit",
  "skeds.past_empty": "Ei menneitä testejä.",
  "skeds.when": "{from} – {to} UTC",
  "skeds.local": "Paikallinen aikasi: {from} – {to}",
  "skeds.ours": "omamme",
  "skeds.join": "Liity",
  "skeds.join_title": "Suunnittele oma testi samaan aikaan samalla taajuudella",
  "skeds.join_label": "Liity testiin: {calls}, {when}",
  "skeds.delete_title": "Poista (ota pois taululta)",
  "skeds.delete_label": "Poista oma testimme, {when}",

  "skeds.post_label": "Suunnittele testi",
  "skeds.day": "Päivä",
  "skeds.time": "Aika (UTC)",
  "skeds.from": "Alkaa",
  "skeds.to": "Päättyy",
  "skeds.until": "–",
  "skeds.frequency": "Taajuus",
  "skeds.frequency_other": "Muu",
  "skeds.dial": "Viritystaajuus",
  "skeds.note": "Huomautus",
  "skeds.post": "Julkaise osoitteessa neo.oh2gba.eu",
  "skeds.chat_title": "Chat",
  "skeds.chat_label": "Rivi chattiin",
  "skeds.chat_send": "Lähetä",
  "skeds.chat_empty": "Mitään ei ole vielä sanottu.",
  "skeds.chat_closed": "Chat on suljettu.",
  "skeds.chat_popup": "HF-testien chat: {call}",
  "skeds.chat_popup_more": {
    one: "HF-testien chat: {n} uusi rivi, lähettäjä {call}",
    other: "HF-testien chat: {n} uutta riviä, viimeisin: {call}",
  },
} as const;
