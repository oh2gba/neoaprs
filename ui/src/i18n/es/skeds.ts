// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Acerca de las pruebas HF",
  "skeds.about1":
    "Para estaciones que prueban APRS en HF: indica cuándo estarás en el aire y en qué frecuencia, para que otra estación pueda hacer pruebas contigo.",
  "skeds.about2": "El tablón es público, en neo.oh2gba.eu. No se envía por radio.",

  "skeds.empty": "No hay pruebas programadas.",
  "skeds.when": "{from} a {to} UTC",
  "skeds.local": "Tu hora: {from} a {to}",
  "skeds.ours": "nuestra",
  "skeds.join": "Unirse",
  "skeds.join_title": "Programar una prueba tuya a la misma hora y en la misma frecuencia",
  "skeds.join_label": "Unirse a la prueba de {calls}, {when}",
  "skeds.delete_title": "Eliminar (quitarla del tablón)",
  "skeds.delete_label": "Eliminar nuestra prueba, {when}",

  "skeds.post_label": "Programar una prueba",
  "skeds.day": "Día",
  "skeds.time": "Hora (UTC)",
  "skeds.from": "Desde",
  "skeds.to": "Hasta",
  "skeds.until": "a",
  "skeds.frequency": "Frecuencia",
  "skeds.frequency_other": "Otra",
  "skeds.dial": "Frecuencia del dial",
  "skeds.note": "Nota",
  "skeds.post": "Publicar en neo.oh2gba.eu",
} as const;
