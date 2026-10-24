import type { objects as en } from "@/i18n/en/objects";
import type { Message } from "@/i18n/message";

export const objects: Readonly<Record<keyof typeof en, Message>> = {
  "schedule.sent": { "=0": "non ancora inviato", "=1": "inviato una volta", other: "inviato {n} volte" },
  "schedule.ended": { "=1": "inviato una volta, concluso", other: "inviato {n} volte, concluso" },
  "schedule.next": { "=0": "non ancora inviato, prossimo {when}", "=1": "inviato una volta, prossimo {when}", other: "inviato {n} volte, prossimo {when}" },
  "schedule.waiting": { "=0": "non ancora inviato, in attesa", "=1": "inviato una volta, in attesa", other: "inviato {n} volte, in attesa" },
  "schedule.killing": { "=0": "rimozione, non ancora inviato", "=1": "rimozione, inviato una volta", other: "rimozione, inviato {n} volte" },

  "objects.new": "Nuovo",
  "objects.none": "Nessun oggetto.",
  "objects.edit": "Modifica",
  "objects.edit_label": "Modifica {name}",
  "objects.delete_title": "Elimina (rimuovi dall’etere)",
  "objects.delete_label": { select: "kind", object: "Elimina l’oggetto {name}", item: "Elimina l’item {name}", other: "Elimina l’oggetto {name}" },
  "objects.kind_word": { select: "kind", object: "oggetto", item: "item", other: "oggetto" },

  "objects.form.new": "Nuovo oggetto",
  "objects.field.name": "Nome",
  "objects.field.kind": "Tipo",
  "objects.field.object": "Oggetto",
  "objects.field.item": "Item",
  "objects.field.lat": "Latitudine",
  "objects.field.lon": "Longitudine",
  "objects.field.comment": "Commento",
  "objects.field.course": "Rotta",
  "objects.field.speed": "Velocità",
  "objects.field.path": "Percorso",
  "objects.unit.deg": "°",
  "objects.form.pick": "Scegli sulla mappa",
  "objects.form.cancel": "Annulla",
  "objects.form.save": "Salva",

  "objects.problem.name_chars": "Niente spazi alle estremità, né ! _ | ~",
  "objects.problem.at_most": "Al massimo {max} caratteri",
  "objects.problem.item_name": "Un item ha da {min} a {max} caratteri",
  "objects.problem.not_number": "Non è un numero",
  "objects.problem.between": "Tra -{max} e {max}",
  "objects.problem.comment_chars": "ASCII stampabile, senza | né ~",
  "objects.problem.course": "Da 0 a {max} gradi",
  "objects.problem.speed": "Da 0 a {max} km/h",
};
