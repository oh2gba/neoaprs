// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Sui test HF",
  "skeds.about1":
    "Per le stazioni che provano l’APRS in HF: indica quando sarai in onda e su quale frequenza, così un’altra stazione può fare un test con te.",
  "skeds.about2": "La bacheca è pubblica, su neo.oh2gba.eu. Non viene inviata via radio.",

  "skeds.empty": "Nessun test in programma.",
  "skeds.past_title": "Test passati",
  "skeds.past_empty": "Nessun test passato.",
  "skeds.when": "{from} fino a {to} UTC",
  "skeds.local": "Ora locale: {from} fino a {to}",
  "skeds.ours": "nostro",
  "skeds.join": "Partecipa",
  "skeds.join_title": "Programma un tuo test allo stesso orario sulla stessa frequenza",
  "skeds.join_label": "Partecipa al test di {calls}, {when}",
  "skeds.delete_title": "Elimina (toglilo dalla bacheca)",
  "skeds.delete_label": "Elimina il nostro test, {when}",

  "skeds.post_label": "Programma un test",
  "skeds.day": "Giorno",
  "skeds.time": "Ora (UTC)",
  "skeds.from": "Dalle",
  "skeds.to": "Alle",
  "skeds.until": "alle",
  "skeds.frequency": "Frequenza",
  "skeds.frequency_other": "Altra",
  "skeds.dial": "Frequenza di sintonia",
  "skeds.note": "Nota",
  "skeds.post": "Pubblica su neo.oh2gba.eu",
  "skeds.chat_title": "Chat",
  "skeds.chat_label": "Una riga per la chat",
  "skeds.chat_send": "Invia",
  "skeds.chat_empty": "Non è stato ancora detto niente.",
  "skeds.chat_closed": "La chat è chiusa.",
  "skeds.chat_popup": "Chat dei test HF: {call}",
  "skeds.chat_popup_more": {
    one: "Chat dei test HF: {n} nuova riga, da {call}",
    other: "Chat dei test HF: {n} nuove righe, l’ultima da {call}",
  },
} as const;
