// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Acerca de los skeds",
  "skeds.about1": "Un sked dice cuándo estarás en el aire y en qué frecuencia, para que otra estación pueda encontrarte allí.",
  "skeds.about2": "El tablón es público, en neo.oh2gba.eu. No se envía por radio.",

  "skeds.empty": "No hay skeds próximos.",
  "skeds.when": "{from} a {to} UTC",
  "skeds.local": "Tu hora: {from} a {to}",
  "skeds.ours": "nuestro",
  "skeds.join": "Unirse",
  "skeds.join_title": "Publicar un sked tuyo a la misma hora y en la misma frecuencia",
  "skeds.join_label": "Unirse al sked de {calls}, {when}",
  "skeds.delete_title": "Eliminar (quitarlo del tablón)",
  "skeds.delete_label": "Eliminar nuestro sked, {when}",

  "skeds.post_label": "Publicar un sked",
  "skeds.day": "Día",
  "skeds.time": "Hora (UTC)",
  "skeds.from": "Desde",
  "skeds.to": "Hasta",
  "skeds.until": "a",
  "skeds.frequency": "Frecuencia",
  "skeds.frequency_other": "Otra",
  "skeds.dial": "Dial",
  "skeds.note": "Nota",
  "skeds.post": "Publicar en neo.oh2gba.eu",
} as const;
