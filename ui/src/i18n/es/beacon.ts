import type { beacon as en } from "@/i18n/en/beacon";
import type { Message } from "@/i18n/message";

export const beacon: Readonly<Record<keyof typeof en, Message>> = {
  "beacon.last_beacon": "Última baliza",
  "beacon.not_yet": "aún no",
  "beacon.beacon_now": "Enviar baliza ahora",
  "beacon.status": "Estado",
  "beacon.send_status_now": "Enviar estado ahora",
  "beacon.really_send": "¿Enviar de verdad?",
  "beacon.rigctld_on": "rigctld activado",
  "beacon.rigctld_off": "rigctld desactivado",
  "beacon.preview": "Vista previa",
  "beacon.preview_empty": "Vista previa: con estos valores aún no hay paquete",
  "beacon.packet": "Paquete",
  "beacon.packet_label": "La baliza tal como se enviaría",
  "beacon.status_label": "El estado tal como se enviaría",
};
