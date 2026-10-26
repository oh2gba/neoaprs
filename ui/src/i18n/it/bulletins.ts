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
  "bulletins.kind.bulletin": "Bollettino",
  "bulletins.kind.announcement": "Annuncio",
  "bulletins.kind.group": "Bollettino a un gruppo",
  "bulletins.kinds_help_label": "Cosa sono i tipi",
  "bulletins.kinds_help":
    "Un bollettino è per tutti e nessuno lo conferma. Un bollettino a un gruppo è per le stazioni che seguono quel nome di gruppo. Per raggiungere stazioni precise, con la conferma di ciascuna, scrivi loro un messaggio: scheda Messaggi, Stazioni.",
  "bulletins.letter": "Lettera",
  "bulletins.number": "Numero",
  "bulletins.group": "Gruppo",
  "bulletins.group_placeholder": "Nome",
  "bulletins.text": "Testo",
  "bulletins.post": "Pubblica",
};
