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
  "bulletins.kind_name.bulletin": "Boletim",
  "bulletins.kind_name.announcement": "Aviso",
  "bulletins.kind_name.group": "Boletim de grupo",
  "bulletins.sent_for": "Enviado por",
  "bulletins.group": "Grupo",
  "bulletins.group_placeholder": "Nome",
  "bulletins.text": "Texto",
  "bulletins.tip.hours": { one: "{n} hora", other: "{n} horas" },
  "bulletins.tip.days": { one: "{n} dia", other: "{n} dias" },
  "bulletins.tip.kinds1":
    "Um boletim e um aviso são exibidos por toda estação que os recebe: o boletim para o que importa agora, o aviso para o que continua valendo por dias.",
  "bulletins.tip.kinds2":
    "Um boletim de grupo é para um só grupo; toda estação o exibe, a menos que o seu operador tenha escolhido outros grupos para exibir.",
  "bulletins.tip.sent_for": "Por quanto tempo a publicação é repetida, contado a partir do primeiro pacote.",
  "bulletins.tip.group1":
    "O nome faz parte do endereço, como em BLN3HAMS, então toda estação recebe o boletim e o exibe, a menos que o seu operador tenha escolhido outros grupos para exibir.",
  "bulletins.tip.group2": "O NeoAPRS exibe os boletins de todos os grupos que recebe, em Mensagens de grupo.",
  "bulletins.tip.text1": "Até {max} caracteres, imprimíveis, nenhum de {forbidden}.",
  "bulletins.tip.text_repeat": "Sai em um único pacote de rádio, repetido pelo tempo escolhido em Enviado por.",
  "bulletins.post": "Publicar",
};
