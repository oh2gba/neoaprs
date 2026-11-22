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
  "bulletins.kind_name.bulletin": "Bollettino",
  "bulletins.kind_name.announcement": "Annuncio",
  "bulletins.kind_name.group": "Bollettino di gruppo",
  "bulletins.sent_for": "Inviato per",
  "bulletins.group": "Gruppo",
  "bulletins.group_placeholder": "Nome",
  "bulletins.text": "Testo",
  "bulletins.tip.hours": { one: "{n} ora", other: "{n} ore" },
  "bulletins.tip.days": { one: "{n} giorno", other: "{n} giorni" },
  "bulletins.tip.kinds1":
    "Un bollettino e un annuncio sono mostrati da ogni stazione che li riceve: un bollettino per ciò che conta adesso, un annuncio per ciò che resta valido per giorni.",
  "bulletins.tip.kinds2":
    "Un bollettino di gruppo è per un solo gruppo; ogni stazione lo mostra, a meno che il suo operatore non abbia scelto altri gruppi da mostrare.",
  "bulletins.tip.sent_for": "Per quanto tempo la pubblicazione viene ripetuta, a partire dal suo primo pacchetto.",
  "bulletins.tip.group1":
    "Il nome fa parte dell’indirizzo, come in BLN3HAMS, così ogni stazione ascolta il bollettino e lo mostra, a meno che il suo operatore non abbia scelto altri gruppi da mostrare.",
  "bulletins.tip.group2": "NeoAPRS mostra i bollettini di ogni gruppo che ascolta, in Messaggi di gruppo.",
  "bulletins.tip.text1": "Fino a {max} caratteri, stampabili, nessuno tra {forbidden}.",
  "bulletins.tip.text_repeat": "Parte in un solo pacchetto radio, ripetuto per il tempo scelto in Inviato per.",
  "bulletins.post": "Pubblica",
};
