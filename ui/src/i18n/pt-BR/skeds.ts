// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Sobre os testes HF",
  "skeds.about1":
    "Para estações que estão testando APRS em HF: diga quando você estará no ar e em qual frequência, para que outra estação possa testar com você.",
  "skeds.about2": "O quadro é público, em neo.oh2gba.eu. Não é enviado por rádio.",

  "skeds.empty": "Nenhum teste marcado.",
  "skeds.past_title": "Testes anteriores",
  "skeds.past_empty": "Nenhum teste anterior.",
  "skeds.when": "{from} até {to} UTC",
  "skeds.local": "Seu horário: {from} até {to}",
  "skeds.ours": "nosso",
  "skeds.join": "Participar",
  "skeds.join_title": "Marcar um teste seu no mesmo horário e na mesma frequência",
  "skeds.join_label": "Participar do teste de {calls}, {when}",
  "skeds.delete_title": "Excluir (tirar do quadro)",
  "skeds.delete_label": "Excluir nosso teste, {when}",
  "skeds.past_delete_label": "Excluir o teste anterior, {when}",

  "skeds.post_label": "Marcar um teste",
  "skeds.day": "Dia",
  "skeds.time": "Hora (UTC)",
  "skeds.from": "De",
  "skeds.to": "Até",
  "skeds.until": "até",
  "skeds.frequency": "Frequência",
  "skeds.frequency_other": "Outra",
  "skeds.dial": "Frequência do dial",
  "skeds.note": "Nota",
  "skeds.post": "Publicar em neo.oh2gba.eu",
  "skeds.chat_title": "Chat",
  "skeds.chat_label": "Uma linha para o chat",
  "skeds.chat_send": "Enviar",
  "skeds.chat_empty": "Nada foi dito ainda.",
  "skeds.chat_closed": "O chat está fechado.",
  "skeds.chat_popup": "Chat dos testes HF: {call}",
  "skeds.chat_popup_more": {
    one: "Chat dos testes HF: {n} linha nova, de {call}",
    other: "Chat dos testes HF: {n} linhas novas, a última de {call}",
  },
} as const;
