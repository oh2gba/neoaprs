// The Objects tab as the page runs it: the form under the list, always there, which adds a new object (nothing selected, the place we are) or changes the one that is selected (`editing`: a click on its row, or Edit on its card), the draft as it is typed,
// the place on the map that the form asks for (`placing`: a click on the map is the place, which `pin` shows meanwhile while the Objects tab is in front), and the commands that make, move and kill an object. The daemon holds the objects (the topic `own_objects`);
// the page only sends what the user did. The form keeps what was typed until the daemon has the object as it was saved (the topic tells it, and the form is blank again): an error of the daemon leaves it for the user to correct. `cancel` (Esc, the Cancel button)
// leaves the selection and clears the form. A blank form follows the place we are, until something is typed. A change from a card opens the Objects tab, wherever it is asked for.
import { computed, reactive, ref, watch, type Ref } from "vue";
import type { Panel } from "@/composables/usePanel";
import { draftOf, emptyDraft, isObjectOf, moveCommand, objectCommand, wrapLongitude, type ObjectDraft } from "@/lib/ownobjects";
import type { Home } from "@/lib/mapview";
import { onEarth, parseNumber } from "@/lib/fieldcheck";
import { degreesText } from "@/lib/setup";
import type { Command, OwnObjectRow } from "@/protocol/protocol";

export function useOwnObjects(rows: ReadonlyMap<string, OwnObjectRow>, home: Ref<Home | null>, send: (command: Command) => boolean, panel: Panel) {
  const editing = ref<string | null>(null); // the name of the object that is selected and being changed; null for a new one
  const placing = ref(false); // a click on the map is the place of the object
  const draft = reactive<ObjectDraft>(emptyDraft(home.value));
  const blank = ref(JSON.stringify(draft)); // the draft of a new object as it stood when the form was last cleared
  const asked = ref<ReturnType<typeof objectCommand>>(null); // what Save sent, until the daemon has it

  /** There is something to leave: an object is selected, or the form holds more than a new object at the place we are. */
  const dirty = computed(() => editing.value !== null || JSON.stringify(draft) !== blank.value);
  const picking = computed(() => placing.value);
  const pin = computed(() => {
    const lat = parseNumber(draft.lat);
    const lon = parseNumber(draft.lon);
    return panel.tab.value === "objects" && lat !== null && lon !== null && onEarth(lat, lon) ? { lat, lon } : null;
  });

  /** The form as a new object: the place we are, the car, no name. */
  function clear(): void {
    Object.assign(draft, emptyDraft(home.value));
    blank.value = JSON.stringify(draft);
    editing.value = null;
    placing.value = false;
    asked.value = null;
  }
  // a form nothing was typed in follows the place we are
  watch(home, () => {
    if (!dirty.value) clear();
  });

  /** The object of this name is selected: the form has what the daemon has of it; the Objects tab in front. */
  function edit(name: string): void {
    const row = rows.get(name);
    if (row === undefined) return;
    Object.assign(draft, draftOf(row));
    editing.value = name;
    placing.value = false;
    asked.value = null;
    panel.show("objects");
  }

  /** Leaves the selection and clears the form (Esc, Cancel, and the end of a save). */
  function cancel(): void {
    clear();
  }

  /** The place from a click on the map: five decimals (a metre). */
  function place(lat: number, lon: number): void {
    draft.lat = degreesText(Math.round(lat * 1e5) / 1e5);
    draft.lon = degreesText(wrapLongitude(lon));
    placing.value = false;
  }

  /** Sends the object as the form has it. The form is blank when the daemon has the object so (at once for one that is there already as the form has it). */
  function save(): void {
    const command = objectCommand(draft);
    if (command === null) return;
    const there = rows.get(command.name);
    if (there !== undefined && isObjectOf(there, command)) cancel();
    else if (send(command)) asked.value = command;
  }

  watch(
    () => (asked.value === null ? undefined : rows.get(asked.value.name)),
    (row) => {
      if (row !== undefined && asked.value !== null && isObjectOf(row, asked.value)) cancel();
    },
  );

  // an object that is gone (killed, forgotten) is no longer selected
  watch(
    () => editing.value !== null && !rows.has(editing.value),
    (gone) => {
      if (gone) cancel();
    },
  );

  function kill(name: string): void {
    send({ cmd: "object_kill", name });
    if (editing.value === name) cancel();
  }

  /** A marker was dragged: the object is where it was dropped. */
  function move(name: string, lat: number, lon: number): void {
    const row = rows.get(name);
    if (row !== undefined) send(moveCommand(row, lat, lon));
  }

  /** The Choose on map button: the next click on the map is the place, or no longer. */
  function togglePlacing(): void {
    placing.value = !placing.value;
  }

  return reactive({ editing, placing, draft, dirty, picking, pin, edit, cancel, place, togglePlacing, save, kill, move });
}

export type OwnObjectsView = ReturnType<typeof useOwnObjects>;
