import type { layersettings as en } from "@/i18n/en/layersettings";
import type { Message } from "@/i18n/message";

export const layersettings: Readonly<Record<keyof typeof en, Message>> = {
  "layers.settings.none": "Nessuno",
  "layers.settings.aircraft_tip_label": "Informazioni sugli aerei",
  "layers.settings.aircraft_tip1": "Da dove vengono gli aerei: un servizio su internet o un ricevitore tuo.",
  "layers.settings.aircraft_tip2": "Gli aerei compaiono sulla mappa quando Aerei è spuntato nel riquadro Livelli.",
  "layers.settings.ships_tip_label": "Informazioni sulle navi",
  "layers.settings.ships_tip1": "Fintraffic copre le acque della Finlandia ed è nell’elenco solo dove la tua mappa le raggiunge. Oppure usa un ricevitore tuo.",
  "layers.settings.ships_tip2": "Le navi compaiono sulla mappa quando Navi è spuntato nel riquadro Livelli.",
  "layers.receiver.own": "Il mio ricevitore",
  "layers.receiver.address": "Indirizzo del ricevitore",
  "layers.receiver.empty": "Questo computer",
  "layers.receiver.radarcape_tip": "L’indirizzo del tuo Radarcape sulla tua rete.",
  "layers.receiver.aircraft_tip_label": "Informazioni sull’indirizzo del ricevitore",
  "layers.receiver.aircraft_tip1":
    "Un ricevitore con readsb, dump1090, tar1090 o PiAware, per esempio su un Raspberry Pi. Scrivi il suo nome, numero o indirizzo web.",
  "layers.receiver.aircraft_tip2": "Lascialo vuoto quando il ricevitore gira su questo computer.",
  "layers.receiver.ships_tip_label": "Informazioni sull’indirizzo del ricevitore",
  "layers.receiver.ships_tip1": "Il nome del computer che invia i messaggi delle navi del tuo ricevitore.",
  "layers.receiver.ships_tip2": "Lascialo vuoto quando il ricevitore gira su questo computer.",
  "layers.receiver.state.looking": "in ricerca",
  "layers.receiver.state.receiving": "in ricezione",
  "layers.receiver.state.no_answer": "nessuna risposta",
  "layers.receiver.line.looking": "Ricerca del ricevitore",
  "layers.receiver.line.no_answer": "Nessuna risposta dal ricevitore",
  "layers.receiver.line.aircraft": { one: "In ricezione: {n} aereo, {span} fa", other: "In ricezione: {n} aerei, {span} fa" },
  "layers.receiver.line.aircraft_none": "In ricezione, ancora nessun aereo",
  "layers.receiver.line.ships": { one: "In ricezione: {n} nave, {span} fa", other: "In ricezione: {n} navi, {span} fa" },
  "layers.receiver.line.ships_none": "Connesso, ancora nessuna nave ricevuta",
};
