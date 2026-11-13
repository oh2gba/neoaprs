// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Informazioni sugli sked",
  "skeds.about1": "Uno sked dice quando sarai in onda e su quale frequenza, così un’altra stazione può incontrarti lì.",
  "skeds.about2": "La bacheca è pubblica, su neo.oh2gba.eu. Non viene inviata via radio.",

  "skeds.empty": "Nessuno sked in programma.",
  "skeds.when": "{from} fino a {to} UTC",
  "skeds.local": "Ora locale: {from} fino a {to}",
  "skeds.ours": "nostro",
  "skeds.join": "Partecipa",
  "skeds.join_title": "Pubblica un tuo sked allo stesso orario sulla stessa frequenza",
  "skeds.join_label": "Partecipa allo sked di {calls}, {when}",
  "skeds.delete_title": "Elimina (toglilo dalla bacheca)",
  "skeds.delete_label": "Elimina il nostro sked, {when}",

  "skeds.post_label": "Pubblica uno sked",
  "skeds.day": "Giorno",
  "skeds.time": "Ora (UTC)",
  "skeds.from": "Dalle",
  "skeds.to": "Alle",
  "skeds.until": "alle",
  "skeds.frequency": "Frequenza",
  "skeds.frequency_other": "Altra",
  "skeds.dial": "Dial",
  "skeds.note": "Nota",
  "skeds.post": "Pubblica su neo.oh2gba.eu",
} as const;
