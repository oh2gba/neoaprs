import type { bulletins as en } from "@/i18n/en/bulletins";
import type { Message } from "@/i18n/message";

export const bulletins: Readonly<Record<keyof typeof en, Message>> = {
  "bulletins.section.announcement": "Anuncios",
  "bulletins.section.bulletin": "Boletines",
  "bulletins.section.group": "Mensajes de grupo",
  "bulletins.section.nws": "Servicio meteorológico",

  "bulletins.empty": "No hay nada en el tablón.",
  "bulletins.about_label": "Sobre los boletines",
  "bulletins.about1": "Un boletín es un mensaje para todos, que se muestra en el tablón de cada estación.",
  "bulletins.about2": "Úsalo para horarios de la red, eventos, avisos.",
  "bulletins.delete_title": "Eliminar (dejar de enviar)",
  "bulletins.delete_own": "Eliminar nuestro boletín {slot}",
  "bulletins.delete": "Eliminar el boletín {slot} de {sender}",
  "bulletins.to": "para",
  "bulletins.ours": "nuestro",
  "bulletins.posted": "publicado {time}",
  "bulletins.heard_title": "escuchado por primera vez {first}, por última vez {last}",
  "bulletins.heard": { "=1": "escuchado una vez, hace {span}", other: "escuchado {n} veces, hace {span}" },

  "bulletins.post_label": "Publicar un boletín",
  "bulletins.kind": "Tipo",
  "bulletins.kind.bulletin": { one: "Boletín (se envía durante {n} hora)", other: "Boletín (se envía durante {n} horas)" },
  "bulletins.kind.announcement": { one: "Anuncio (se envía durante {n} día)", other: "Anuncio (se envía durante {n} días)" },
  "bulletins.kind.group": {
    one: "Boletín de grupo (para un grupo, se envía durante {n} hora)",
    other: "Boletín de grupo (para un grupo, se envía durante {n} horas)",
  },
  "bulletins.letter": "Letra",
  "bulletins.number": "Número",
  "bulletins.group": "Grupo",
  "bulletins.group_placeholder": "Nombre",
  "bulletins.text": "Texto",
  "bulletins.post": "Publicar",
  "bulletins.replace": "Sustituir",
};
