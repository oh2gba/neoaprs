import type { bulletins as en } from "@/i18n/en/bulletins";
import type { Message } from "@/i18n/message";

export const bulletins: Readonly<Record<keyof typeof en, Message>> = {
  "bulletins.section.announcement": "Annunci",
  "bulletins.section.bulletin": "Bollettini",
  "bulletins.section.group": "Messaggi di gruppo",
  "bulletins.section.nws": "Servizio meteo",

  "bulletins.empty": "Niente in bacheca.",
  "bulletins.about_label": "Sui bollettini",
  "bulletins.about1": "Un bollettino è un messaggio per tutti, mostrato nella bacheca di ogni stazione.",
  "bulletins.about2": "Usalo per gli orari del net, gli eventi, gli avvisi.",
  "bulletins.delete_title": "Elimina (smetti di inviare)",
  "bulletins.delete_own": "Elimina il nostro bollettino {slot}",
  "bulletins.delete": "Elimina il bollettino {slot} di {sender}",
  "bulletins.to": "a",
  "bulletins.ours": "nostro",
  "bulletins.posted": "pubblicato {time}",
  "bulletins.heard_title": "ricevuto la prima volta {first}, l’ultima {last}",
  "bulletins.heard": { "=1": "ricevuto una volta, {span} fa", other: "ricevuto {n} volte, {span} fa" },

  "bulletins.post_label": "Pubblica un bollettino",
  "bulletins.kind": "Tipo",
  "bulletins.kind.bulletin": { one: "Bollettino (inviato per {n} ora)", other: "Bollettino (inviato per {n} ore)" },
  "bulletins.kind.announcement": { one: "Annuncio (inviato per {n} giorno)", other: "Annuncio (inviato per {n} giorni)" },
  "bulletins.kind.group": { one: "Bollettino di gruppo (a un gruppo, inviato per {n} ora)", other: "Bollettino di gruppo (a un gruppo, inviato per {n} ore)" },
  "bulletins.letter": "Lettera",
  "bulletins.number": "Numero",
  "bulletins.group": "Gruppo",
  "bulletins.group_placeholder": "Nome",
  "bulletins.text": "Testo",
  "bulletins.post": "Pubblica",
  "bulletins.replace": "Sostituisci",
};
