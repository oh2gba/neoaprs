// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { skeds as source } from "@/i18n/en/skeds";
import type { Message } from "@/i18n/message";

export const skeds: Record<keyof typeof source, Message> = {
  "skeds.about_label": "Sobre os skeds",
  "skeds.about1": "Um sked diz quando você estará no ar e em qual frequência, para que outra estação possa encontrar você lá.",
  "skeds.about2": "O quadro é público, em neo.oh2gba.eu. Não é enviado por rádio.",

  "skeds.empty": "Nenhum sked por vir.",
  "skeds.when": "{from} até {to} UTC",
  "skeds.local": "Seu horário: {from} até {to}",
  "skeds.ours": "nosso",
  "skeds.join": "Participar",
  "skeds.join_title": "Publicar um sked seu no mesmo horário e na mesma frequência",
  "skeds.join_label": "Participar do sked de {calls}, {when}",
  "skeds.delete_title": "Excluir (tirar do quadro)",
  "skeds.delete_label": "Excluir nosso sked, {when}",

  "skeds.post_label": "Publicar um sked",
  "skeds.day": "Dia",
  "skeds.time": "Hora (UTC)",
  "skeds.from": "De",
  "skeds.to": "Até",
  "skeds.until": "até",
  "skeds.frequency": "Frequência",
  "skeds.frequency_other": "Outra",
  "skeds.dial": "Dial",
  "skeds.note": "Nota",
  "skeds.post": "Publicar em neo.oh2gba.eu",
} as const;
