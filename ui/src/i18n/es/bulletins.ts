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
  "bulletins.kind_name.bulletin": "Boletín",
  "bulletins.kind_name.announcement": "Anuncio",
  "bulletins.kind_name.group": "Boletín de grupo",
  "bulletins.sent_for": "Enviado durante",
  "bulletins.group": "Grupo",
  "bulletins.group_placeholder": "Nombre",
  "bulletins.text": "Texto",
  "bulletins.tip.hours": { one: "{n} hora", other: "{n} horas" },
  "bulletins.tip.days": { one: "{n} día", other: "{n} días" },
  "bulletins.tip.kinds1":
    "Un boletín y un anuncio los muestra cada estación que los escucha: un boletín para lo que importa ahora, un anuncio para lo que sigue siendo cierto durante días.",
  "bulletins.tip.kinds2":
    "Un boletín de grupo es para un solo grupo; cada estación lo muestra salvo que su operador haya elegido otros grupos.",
  "bulletins.tip.sent_for": "Cuánto tiempo se repite la publicación, contado desde su primer paquete.",
  "bulletins.tip.group1":
    "El nombre forma parte de la dirección, como en BLN3HAMS, así que cada estación escucha el boletín y lo muestra, salvo que su operador haya elegido otros grupos.",
  "bulletins.tip.group2": "NeoAPRS muestra los boletines de todos los grupos que escucha, en Mensajes de grupo.",
  "bulletins.tip.text1": "Hasta {max} caracteres imprimibles, sin ninguno de {forbidden}.",
  "bulletins.tip.text_repeat":
    "Sale en un solo paquete de radio, repetido durante el tiempo elegido en Enviado durante.",
  "bulletins.post": "Publicar",
};
