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
  "bulletins.kind.bulletin": "Boletín",
  "bulletins.kind.announcement": "Anuncio",
  "bulletins.kind.group": "Boletín a un grupo",
  "bulletins.kinds_help_label": "Qué son los tipos",
  "bulletins.kinds_help": "Todos ven un boletín y nadie acusa recibo. Un boletín de grupo es para las estaciones que siguen ese nombre.",
  "bulletins.letter": "Letra",
  "bulletins.number": "Número",
  "bulletins.group": "Grupo",
  "bulletins.group_placeholder": "Nombre",
  "bulletins.text": "Texto",
  "bulletins.slot_tip": "El lugar en el tablón. Publicar de nuevo en el mismo lo sustituye.",
  "bulletins.group_tip": "El grupo al que va dirigido, hasta {max} letras y dígitos. Las estaciones que siguen ese nombre lo muestran.",
  "bulletins.text_tip": "El texto del boletín. El contador muestra cuántos caracteres quedan.",
  "bulletins.post": "Publicar",
};
