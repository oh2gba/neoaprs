import type { bulletins as en } from "@/i18n/en/bulletins";
import type { Message } from "@/i18n/message";

export const bulletins: Readonly<Record<keyof typeof en, Message>> = {
  "bulletins.section.announcement": "Anuncios",
  "bulletins.section.bulletin": "Boletines",
  "bulletins.section.group": "Mensajes de grupo",
  "bulletins.section.nws": "Servicio meteorológico",

  "bulletins.empty": "No hay nada en el tablón.",
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
  "bulletins.kinds_help":
    "Un boletín es para todos y nadie acusa recibo. Un boletín a un grupo es para las estaciones que siguen ese nombre de grupo. Para llegar a estaciones concretas, con acuse de cada una, envíales un mensaje: pestaña Mensajes, Estaciones.",
  "bulletins.letter": "Letra",
  "bulletins.number": "Número",
  "bulletins.group": "Grupo",
  "bulletins.group_placeholder": "Nombre",
  "bulletins.text": "Texto",
  "bulletins.post": "Publicar",
};
