// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { beacon as source } from "@/i18n/en/beacon";
import type { Message } from "@/i18n/message";

export const beacon: Record<keyof typeof source, Message> = {
  "beacon.last_beacon": "Último beacon",
  "beacon.not_yet": "ainda não",
  "beacon.beacon_now": "Beacon agora",
  "beacon.status": "Status",
  "beacon.send_status_now": "Enviar status agora",
  "beacon.really_send": "Enviar mesmo?",
  "beacon.rigctld_on": "rigctld ligado",
  "beacon.rigctld_off": "rigctld desligado",
  "beacon.preview": "Prévia",
  "beacon.preview_empty": "Prévia: estes valores ainda não formam um pacote",
  "beacon.packet": "Pacote",
  "beacon.packet_label": "O beacon como seria enviado",
  "beacon.status_label": "O status como seria enviado",
};
