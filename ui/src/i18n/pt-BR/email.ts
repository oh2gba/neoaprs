// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { email as source } from "@/i18n/en/email";
import type { Message } from "@/i18n/message";

export const email: Record<keyof typeof source, Message> = {
  "email.compose": "E-mail",
  "email.to": "Para {address}",
  "email.from": "De {address}",
  "email.checked": "E-mail verificado",

  "email.none": "Nenhum e-mail ainda.",
  "email.list": "E-mails",
  "email.delete": "Excluir: {title}",

  "email.check": "Verificar e-mail",
  "email.checking": "Já está verificando",
  "email.about": "Sobre o e-mail",
  "email.about_gateway":
    'O e-mail passa pelo gateway de internet EMAIL-2 por meio de um iGate, então um e-mail pode aparecer como "{unconfirmed}" mesmo tendo chegado.',
  "email.about_check": '"{check}" pede ao gateway os e-mails que ele guardou para você (ele os guarda por 24 horas).',

  "email.field.to": "Para",
  "email.field.address": "Endereço de e-mail",
  "email.field.text": "Texto",
  "email.used_before": "Já usados",
  "email.forget": "Esquecer {address}",
  "email.send": "Enviar",

  "email.state.waiting": "Aguardando o rádio",
  "email.state.sending": "Enviando ({attempt} de {max})",
  "email.state.delivered": "Entregue",
  "email.state.rejected": "Rejeitado",
  "email.state.cancelled": "Cancelado",
  "email.state.unconfirmed": "Não confirmado",
  "email.not_confirmed": "enviado, não confirmado: o ack do gateway só chega por um iGate, então o e-mail pode muito bem ter sido entregue",

  "email.date_time": "{day} {month} {time}",
};
