// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { objects as source } from "@/i18n/en/objects";
import type { Message } from "@/i18n/message";

export const objects: Record<keyof typeof source, Message> = {
  "schedule.sent": { "=0": "ainda não enviado", "=1": "enviado uma vez", other: "enviado {n} vezes" },
  "schedule.ended": { "=1": "enviado uma vez, encerrado", other: "enviado {n} vezes, encerrado" },
  "schedule.next": { "=0": "ainda não enviado, próximo {when}", "=1": "enviado uma vez, próximo {when}", other: "enviado {n} vezes, próximo {when}" },
  "schedule.waiting": { "=0": "ainda não enviado, aguardando", "=1": "enviado uma vez, aguardando", other: "enviado {n} vezes, aguardando" },
  "schedule.killing": { "=0": "encerrando, ainda não enviado", "=1": "encerrando, enviado uma vez", other: "encerrando, enviado {n} vezes" },
  "schedule.on_request": "enviado só quando pedido",

  "objects.none": "Nenhum objeto.",
  "objects.list": "Nossos objetos",
  "objects.edit_label": "Editar {name}",
  "objects.delete_title": "Excluir (encerrar no ar)",
  "objects.delete_label": { select: "kind", object: "Excluir o objeto {name}", item: "Excluir o item {name}", other: "Excluir o objeto {name}" },
  "objects.kind_word": { select: "kind", object: "objeto", item: "item", other: "objeto" },
  "objects.in_group": "grupo QRU {group}",

  "objects.form.new": "Novo objeto",
  "objects.field.name": "Nome",
  "objects.field.comment": "Comentário",
  "objects.field.course": "Rumo",
  "objects.field.speed": "Velocidade",
  "objects.field.moving": "Em movimento",
  "objects.field.path": "Caminho",
  "objects.field.qru": "Grupo QRU",
  "objects.field.on_request": "Enviar só quando pedido",
  "objects.unit.deg": "graus",
  "objects.form.cancel": "Cancelar",
  "objects.form.save": "Salvar",
  "objects.form.add": "Adicionar",

  "objects.problem.name_chars": "Sem espaço nas pontas, nem ! _ | ~",
  "objects.problem.at_most": "No máximo {max} caracteres",
  "objects.problem.item_name": "Um item tem de {min} a {max} caracteres",
  "objects.problem.not_number": "Não é um número",
  "objects.problem.between": "Entre -{max} e {max}",
  "objects.problem.comment_chars": "ASCII imprimível, sem | nem ~",
  "objects.problem.course": "0 a {max} graus",
  "objects.problem.speed": "0 a {max} km/h",
  "objects.problem.qru_group": "Até {max} letras e dígitos, nem INFO nem NEXT",
};
