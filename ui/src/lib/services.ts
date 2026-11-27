// The ready-made messages to service stations (MessageServices.vue): the addressee and the fixed
// start of the text, which the operator completes and sends as an ordinary message. Formats:
// APRS Thursday (aprs.world/aprsthursday), ANSRVR's CQ, APRS OTA's handbook (aprsota.org).
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";

export interface Service {
  id: string;
  /** the entry as the list says it: the service's own name, shown as it is, or words */
  name: { own: string } | { words: MessageId };
  /** the name of the service the entry belongs to, a group of the list */
  group?: string;
  to: string;
  text: string;
}

export const SERVICES: readonly [Service, ...Service[]] = [
  { id: "aprs_thursday", name: { own: "APRS Thursday" }, to: "ANSRVR", text: "CQ HOTG " },
  { id: "ansrvr", name: { own: "ANSRVR" }, to: "ANSRVR", text: "CQ " },
  { id: "ota_cq", name: { words: "messages.service.ota_cq" }, group: "APRS OTA", to: "OTA", text: "CQ" },
  { id: "ota_chase", name: { words: "messages.service.ota_chase" }, group: "APRS OTA", to: "OTA", text: "CHASE " },
  { id: "ota_host", name: { words: "messages.service.ota_host" }, group: "APRS OTA", to: "OTA", text: "HOST " },
];

/** The entries in the order offered: those of no group, then each group with its entries. */
export function serviceGroups(): { group: string | null; services: Service[] }[] {
  const groups: { group: string | null; services: Service[] }[] = [];
  for (const service of SERVICES) {
    const group = service.group ?? null;
    const last = groups.at(-1);
    if (last !== undefined && last.group === group) last.services.push(service);
    else groups.push({ group, services: [service] });
  }
  return groups;
}

export const serviceName = (service: Service): string =>
  "own" in service.name ? service.name.own : t(service.name.words);
