// What the parts with a Send on share: why nothing may go on its radios, their names in a line, and the title of a path that none of them carries (Ask around in Nearby, Local info in Objects, the Post box of Bulletins);
// and the Send on bound to a draft, which the thing's own Save or Post applies (an object's, a bulletin's): the radios in force of a stored set, its ticks, and the set after a tick.
import { t } from "@/i18n";
import { notConnectedWhy, type SendOnTick } from "@/lib/beaconstatus";
import { radioBlockedReason } from "@/lib/compose";
import type { PageRadio, RadioId } from "@/lib/radios";

/** Why nothing may go on these radios: none of them is connected (one radio: as every button says it, named where it is named; several: a line for each, "FM: not connected"), or there is none; undefined while one
 * is connected, and while `told` is false (before the daemon has told its radios). */
export function radiosBlockedReason(on: readonly PageRadio[], named: (id: RadioId) => boolean, told: boolean): string | undefined {
  if (!told || on.some((radio) => radio.connected)) return undefined;
  const [one] = on;
  return on.length > 1 ? notConnectedWhy(on) : radioBlockedReason(one, one !== undefined && named(one.id), told);
}

/** The names of the radios something went on, for the front of its line ("FM, Mercury"): those that are named (several radios on, or a radio that is off); "" while none is, and nothing is named. */
export function radiosNamed(ids: readonly RadioId[], byId: (id: RadioId) => PageRadio | undefined, named: (id: RadioId) => boolean): string {
  return ids
    .filter(named)
    .map((id) => byId(id)?.name ?? "")
    .filter((name) => name !== "")
    .join(", ");
}

/** Why the fold of a path is greyed while none of these radios carries one, as Route says it ("Mercury: no path"); undefined for no radio. */
export function radiosPathless(on: readonly PageRadio[]): string | undefined {
  return on.length === 0 ? undefined : t("radio.no_path", { name: on.map((radio) => radio.name).join(", ") });
}

/** The radios a thing with its own set goes out on now (an object's, a bulletin's: neoaprs/radiospec.py `in_force_set`), in the order of the boxes (`on`, the radios that are on and can send): with one radio on, that
 * one whatever the set says; else those of the set that are on; none while none of them is (ticked nowhere: the thing waits). */
export function inForce(own: readonly RadioId[], on: readonly RadioId[]): RadioId[] {
  return on.length === 1 ? [...on] : on.filter((id) => own.includes(id));
}

/** The set after a tick of `id` in a Send on bound to a draft, ascending: the radio is added, or taken off (never the last in force: its tick is greyed). A radio of the set that is off stays in it while one of
 * the set is on (it counts again when it is on); a set none of whose radios is on is replaced by the tick. */
export function ticked(own: readonly RadioId[], on: readonly RadioId[], id: RadioId): RadioId[] {
  const base = own.some((radio) => on.includes(radio)) ? own : [];
  const next = base.includes(id) ? base.filter((radio) => radio !== id) : [...base, id];
  return next.sort((a, b) => a - b);
}

/** The ticks of a Send on bound to a draft (SendOn.vue): one for each radio that is on and can send, in the order of the boxes, ticked while the draft's set has it in force (`own`); the one tick left ticked is greyed,
 * so that the thing always goes out somewhere. With none in force no tick is ticked and none is greyed. `name` keeps the ticks of two forms apart (their keys: `post/2`). */
export function draftTicks(senders: readonly PageRadio[], own: readonly RadioId[], name: string): SendOnTick[] {
  const shown = inForce(
    own,
    senders.map((radio) => radio.id),
  );
  return senders.map((radio) => ({
    id: radio.id,
    key: `${name}/${radio.id}`,
    name: radio.name,
    on: shown.includes(radio.id),
    last: shown.length === 1 && shown[0] === radio.id,
  }));
}
