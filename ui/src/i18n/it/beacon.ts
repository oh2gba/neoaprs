import type { beacon as en } from "@/i18n/en/beacon";
import type { Message } from "@/i18n/message";

export const beacon: Readonly<Record<keyof typeof en, Message>> = {
  "beacon.last_beacon": "Ultimo beacon",
  "beacon.not_yet": "non ancora",
  "beacon.beacon_now": "Invia beacon ora",
  "beacon.status": "Stato",
  "beacon.send_status_now": "Invia stato ora",
  "beacon.really_send": "Inviare davvero?",
  "beacon.rigctld_on": "rigctld attivo",
  "beacon.rigctld_off": "rigctld spento",
  "beacon.preview": "Anteprima",
  "beacon.preview_empty": "Anteprima: con questi valori non c’è ancora alcun pacchetto",
  "beacon.packet": "Pacchetto",
  "beacon.packet_label": "Il beacon così come verrebbe inviato",
  "beacon.status_label": "Lo stato così come verrebbe inviato",
};
