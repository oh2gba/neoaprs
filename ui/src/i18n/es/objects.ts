import type { objects as en } from "@/i18n/en/objects";
import type { Message } from "@/i18n/message";

export const objects: Readonly<Record<keyof typeof en, Message>> = {
  "schedule.sent": { "=0": "aún no enviado", "=1": "enviado una vez", other: "enviado {n} veces" },
  "schedule.ended": { "=1": "enviado una vez, terminado", other: "enviado {n} veces, terminado" },
  "schedule.next": { "=0": "aún no enviado, próximo {when}", "=1": "enviado una vez, próximo {when}", other: "enviado {n} veces, próximo {when}" },
  "schedule.waiting": { "=0": "aún no enviado, en espera", "=1": "enviado una vez, en espera", other: "enviado {n} veces, en espera" },
  "schedule.killing": { "=0": "retirando, aún no enviado", "=1": "retirando, enviado una vez", other: "retirando, enviado {n} veces" },
  "schedule.on_request": "enviado solo cuando se pide",

  "objects.none": "No hay objetos.",
  "objects.list": "Objetos",
  "objects.edit_label": "Editar {name}",
  "objects.delete_title": "Eliminar (retirar del aire)",
  "objects.delete_label": { select: "kind", object: "Eliminar el objeto {name}", item: "Eliminar el ítem {name}", other: "Eliminar el objeto {name}" },
  "objects.kind_word": { select: "kind", object: "objeto", item: "ítem", other: "objeto" },
  "objects.in_group": "grupo QRU {group}",

  "objects.form.new": "Nuevo objeto",
  "objects.field.name": "Nombre",
  "objects.field.comment": "Comentario",
  "objects.field.course": "Rumbo",
  "objects.field.speed": "Velocidad",
  "objects.field.moving": "En movimiento",
  "objects.field.path": "Ruta",
  "objects.field.qru": "Grupo QRU",
  "objects.field.on_request": "Enviar solo cuando se pida",
  "objects.unit.deg": "°",
  "objects.form.cancel": "Cancelar",
  "objects.form.save": "Guardar",
  "objects.form.add": "Añadir",

  "objects.problem.name_chars": "Sin espacios en los extremos ni ! _ | ~",
  "objects.problem.at_most": "Máximo {max} caracteres",
  "objects.problem.item_name": "Un ítem tiene de {min} a {max} caracteres",
  "objects.problem.not_number": "No es un número",
  "objects.problem.between": "Entre -{max} y {max}",
  "objects.problem.comment_chars": "ASCII imprimible, sin | ni ~",
  "objects.problem.course": "0 a {max} grados",
  "objects.problem.speed": "0 a {max} km/h",
  "objects.problem.qru_group": "Hasta {max} letras y dígitos, no INFO ni NEXT",
};
