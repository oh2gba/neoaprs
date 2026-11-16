// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { bulletins as source } from "@/i18n/en/bulletins";
import type { Message } from "@/i18n/message";

export const bulletins: Record<keyof typeof source, Message> = {
  "bulletins.section.announcement": "Avisos",
  "bulletins.section.bulletin": "Boletins",
  "bulletins.section.group": "Mensagens de grupo",
  "bulletins.section.nws": "Serviço meteorológico",

  "bulletins.empty": "Nada no mural.",
  "bulletins.about_label": "Sobre boletins",
  "bulletins.about1": "Um boletim é uma mensagem para todos, exibida no mural de cada estação.",
  "bulletins.about2": "Use para horários de rede, eventos, avisos.",
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
  "bulletins.kind.bulletin": { one: "Boletim (enviado por {n} hora)", other: "Boletim (enviado por {n} horas)" },
  "bulletins.kind.announcement": { one: "Aviso (enviado por {n} dia)", other: "Aviso (enviado por {n} dias)" },
  "bulletins.kind.group": { one: "Boletim de grupo (para um grupo, enviado por {n} hora)", other: "Boletim de grupo (para um grupo, enviado por {n} horas)" },
  "bulletins.letter": "Letra",
  "bulletins.number": "Número",
  "bulletins.group": "Grupo",
  "bulletins.group_placeholder": "Nome",
  "bulletins.text": "Texto",
  "bulletins.post": "Publicar",
  "bulletins.replace": "Substituir",
};
