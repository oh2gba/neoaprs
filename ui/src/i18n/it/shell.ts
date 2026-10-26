import type { shell as en } from "@/i18n/en/shell";
import type { Message } from "@/i18n/message";

export const shell: Readonly<Record<keyof typeof en, Message>> = {
  "common.dismiss": "Chiudi",

  "header.project_title": "La pagina del progetto NeoAPRS",
  "header.receive_only": "Solo ricezione",
  "header.receive_only_title":
    "Non si trasmette nulla: questa stazione è impostata in sola ricezione. È l’impostazione station/transmit del servizio, che non è in questa pagina; neoaprs db set station/transmit true la cambia al prossimo avvio",
  "header.no_call": "nessun nominativo",
  "header.no_call_title": "Non si trasmette nulla finché non è impostato un nominativo: apri la configurazione guidata",
  "header.unread_open": {
    one: "{n} messaggio non visto: apri i messaggi",
    other: "{n} messaggi non visti: apri i messaggi",
  },

  "unread.not_seen": { one: "{n} messaggio non visto", other: "{n} messaggi non visti" },
  "unread.new_bulletins": { one: "{n} nuovo bollettino", other: "{n} nuovi bollettini" },

  "tab.messages": "Messaggi",
  "tab.stations": "Stazioni",
  "tab.nearby": "Vicinanze",
  "tab.email": "Email",
  "tab.bulletins": "Bollettini",
  "tab.objects": "Oggetti",
  "tab.beacon": "Beacon",
  "tab.packets": "Pacchetti",
  "tab.settings": "Impostazioni",
  "tab.more": "Altro",
  "tab.menu_new": ", nuovi: {n}",

  "panel.label": "Dettagli",
  "panel.map": "Mappa",
  "panel.width": "Larghezza del pannello",
  "panel.show": "Mostra il pannello",
  "panel.hide": "Nascondi il pannello",
  "panel.show_unseen": "Mostra il pannello, {unseen}",

  "footer.cost": "NeoAPRS usa il {cpu} % di un core del processore e {mb} MB di memoria, in funzione da {span}",
  "footer.cost_no_memory": "NeoAPRS usa il {cpu} % di un core del processore, in funzione da {span}",
  "footer.update": "Aggiorna a {version}",
  "footer.offline": "Servizio offline",
  "footer.connecting": "Connessione…",
  "footer.radio.waiting": "Radio: in attesa…",
  "footer.radio.waiting_title": "ancora nessuna notizia dal TNC",
  "footer.radio.silent": "Radio: silenziosa",
  "footer.radio.entering_kiss": "Radio: passaggio in KISS…",
  "footer.radio.searching": "Radio: ricerca…",
  "footer.radio.not_connected": "Radio: non connessa",
  "footer.radio.open_settings": "Apri le impostazioni della radio",

  "settings.language.label": "Lingua",
};
