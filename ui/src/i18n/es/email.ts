import type { email as en } from "@/i18n/en/email";
import type { Message } from "@/i18n/message";

export const email: Readonly<Record<keyof typeof en, Message>> = {
  "email.compose": "Correo",
  "email.to": "Para {address}",
  "email.from": "De {address}",
  "email.checked": "Correo consultado",

  "email.none": "Aún no hay correo.",
  "email.list": "Correo",
  "email.delete": "Eliminar: {title}",

  "email.check": "Consultar correo",
  "email.checking": "Ya consultando",
  "email.about": "Acerca del correo",
  "email.about_gateway":
    "El correo pasa por la pasarela de internet EMAIL-2 a través de un iGate, así que un correo puede aparecer como {unconfirmed} aunque haya llegado.",
  "email.about_check": "{check} pide a la pasarela el correo que guardó para ti (lo guarda durante 24 horas).",

  "email.field.to": "Para",
  "email.field.address": "Dirección de correo",
  "email.field.text": "Texto",
  "email.used_before": "Usadas antes",
  "email.forget": "Olvidar {address}",
  "email.send": "Enviar",

  "email.state.waiting": "Esperando a la radio",
  "email.state.sending": "Enviando ({attempt} de {max})",
  "email.state.delivered": "Entregado",
  "email.state.rejected": "Rechazado",
  "email.state.cancelled": "Cancelado",
  "email.state.unconfirmed": "Sin confirmar",
  "email.not_confirmed": "enviado, sin confirmar: el acuse de la pasarela solo te llega a través de un iGate, así que es posible que el correo haya salido",

  "email.date_time": "{day} {month} {time}",
};
