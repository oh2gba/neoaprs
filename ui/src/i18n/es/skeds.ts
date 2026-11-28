// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Acerca de las pruebas HF",
  "skeds.about1":
    "Para estaciones que prueban APRS en HF: indica cuándo estarás en el aire y en qué frecuencia, para que otra estación pueda hacer pruebas contigo.",
  "skeds.about2": "El tablón es público, en neo.oh2gba.eu. No se envía por radio.",

  "skeds.empty": "No hay pruebas programadas.",
  "skeds.past_title": "Pruebas anteriores",
  "skeds.past_empty": "No hay pruebas anteriores.",
  "skeds.when": "{from} a {to} UTC",
  "skeds.local": "Tu hora: {from} a {to}",
  "skeds.ours": "nuestra",
  "skeds.join": "Unirse",
  "skeds.join_title": "Programar una prueba tuya a la misma hora y en la misma frecuencia",
  "skeds.join_label": "Unirse a la prueba de {calls}, {when}",
  "skeds.delete_title": "Eliminar (quitarla del tablón)",
  "skeds.delete_label": "Eliminar nuestra prueba, {when}",
  "skeds.past_delete_label": "Eliminar la prueba anterior, {when}",

  "skeds.post_label": "Programar una prueba",
  "skeds.cancel": "Cancelar",
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
  "skeds.chat_title": "Chat",
  "skeds.chat_label": "Una línea para el chat",
  "skeds.chat_send": "Enviar",
  "skeds.chat_empty": "Todavía no se ha dicho nada.",
  "skeds.chat_closed": "El chat está cerrado.",
  "skeds.chat_popup": "Chat de pruebas HF: {call}",
  "skeds.chat_popup_more": {
    one: "Chat de pruebas HF: {n} línea nueva, de {call}",
    other: "Chat de pruebas HF: {n} líneas nuevas, la última de {call}",
  },
} as const;
