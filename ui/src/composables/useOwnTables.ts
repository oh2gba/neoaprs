// The tables of rows the page reads of what we send of our own accord: `own_objects` (by name) and
// `own_bulletins` (by slot).
import { shallowReactive } from "vue";
import { fillTable, type Store } from "@/lib/hub";
import type { OwnBulletinRow, OwnObjectRow } from "@/protocol/protocol";

type OwnHandlers = Pick<
  Store,
  "replaceOwnObjects" | "replaceOwnBulletins" | "setOwnObject" | "setOwnBulletin" | "delOwnObject" | "delOwnBulletin"
>;

export function useOwnTables() {
  const ownObjects = shallowReactive(new Map<string, OwnObjectRow>());
  const ownBulletins = shallowReactive(new Map<string, OwnBulletinRow>());
  const handlers: OwnHandlers = {
    replaceOwnObjects: (rows) => fillTable(ownObjects, rows),
    replaceOwnBulletins: (rows) => fillTable(ownBulletins, rows),
    setOwnObject: (name, row) => void ownObjects.set(name, row),
    setOwnBulletin: (slot, row) => void ownBulletins.set(slot, row),
    delOwnObject: (name) => void ownObjects.delete(name),
    delOwnBulletin: (slot) => void ownBulletins.delete(slot),
  };
  return { ownObjects, ownBulletins, handlers };
}
