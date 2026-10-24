// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { bulletins as source } from "@/i18n/en/bulletins";
import type { Message } from "@/i18n/message";

export const bulletins: Record<keyof typeof source, Message> = {
  "bulletins.section.announcement": "Avisos",
  "bulletins.section.bulletin": "Boletins",
  "bulletins.section.group": "Mensagens de grupo",
  "bulletins.section.nws": "Serviço meteorológico",

  "bulletins.empty": "Nada no mural.",
  "bulletins.delete_title": "Excluir (parar de enviar)",
  "bulletins.delete_own": "Excluir o nosso boletim {slot}",
  "bulletins.delete": "Excluir o boletim {slot} de {sender}",
  "bulletins.to": "para",
  "bulletins.ours": "nosso",
  "bulletins.posted": "publicado {time}",
  "bulletins.heard_title": "recebido pela primeira vez {first}, pela última vez {last}",
  "bulletins.heard": { "=1": "recebido uma vez, há {span}", other: "recebido {n} vezes, há {span}" },

  "bulletins.post_label": "Publicar um boletim",
  "bulletins.kind": "Tipo",
  "bulletins.kind.bulletin": "Boletim",
  "bulletins.kind.announcement": "Aviso",
  "bulletins.kind.group": "Boletim para um grupo",
  "bulletins.kinds_help_label": "O que são os tipos",
  "bulletins.kinds_help":
    "Um boletim é para todos e ninguém o confirma. Um boletim para um grupo é para as estações que acompanham aquele nome de grupo. Para falar com estações específicas, com confirmação de cada uma, envie-lhes uma mensagem: aba Mensagens, Estações.",
  "bulletins.letter": "Letra",
  "bulletins.number": "Número",
  "bulletins.group": "Grupo",
  "bulletins.group_placeholder": "Nome",
  "bulletins.text": "Texto",
  "bulletins.post": "Publicar",
};
