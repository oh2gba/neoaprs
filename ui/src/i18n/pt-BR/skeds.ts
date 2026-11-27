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
} as const;
