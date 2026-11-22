// The Objects tab: the form under the list, which adds a new object or changes the selected one
// (`editing`), the draft, the radios it goes out on, the place the form asks for (`placing`; `pin`
// shows it meanwhile) and the commands that make, move and kill an object. The daemon holds the
// objects (topic `own_objects`). The form keeps what was typed until the daemon has the object
// as saved, so a daemon error leaves it for correction. `cancel` leaves the selection and clears
// the form. The map moves only for a picked place or a selected object. A change from a card
// opens the Objects tab.
import { computed, reactive, ref, watch } from "vue";
import type { Panel } from "@/composables/usePanel";
import { draftOf, emptyDraft, isObjectOf, moveCommand, objectCommand, type ObjectDraft } from "@/lib/ownobjects";
import { onEarth, parseNumber } from "@/lib/fieldcheck";
import type { RadioId } from "@/lib/radios";
import { degreesText, roundPlace, wrapLongitude } from "@/lib/setup";
import type { Command, OwnObjectRow } from "@/protocol/protocol";

export function useOwnObjects(rows: ReadonlyMap<string, OwnObjectRow>, send: (command: Command) => boolean, panel: Panel) {
  const editing = ref<string | null>(null);
  const placing = ref(false);
  const draft = reactive<ObjectDraft>(emptyDraft());
  const blank = ref(JSON.stringify(draft));
  const asked = ref<ReturnType<typeof objectCommand>>(null);

  const dirty = computed(() => editing.value !== null || JSON.stringify(draft) !== blank.value);
  const picking = computed(() => placing.value);
  const pin = computed(() => {
    const lat = parseNumber(draft.lat);
    const lon = parseNumber(draft.lon);
    return panel.tab.value === "objects" && lat !== null && lon !== null && onEarth(lat, lon) ? { lat, lon } : null;
  });

  function clear(): void {
    Object.assign(draft, emptyDraft());
    blank.value = JSON.stringify(draft);
    editing.value = null;
    placing.value = false;
    asked.value = null;
  }

  function edit(name: string): void {
    const row = rows.get(name);
    if (row === undefined) return;
    Object.assign(draft, draftOf(row));
    editing.value = name;
    placing.value = false;
    asked.value = null;
    panel.show("objects");
  }

  function cancel(): void {
    clear();
  }

  function place(lat: number, lon: number): void {
    draft.lat = degreesText(roundPlace(lat));
    draft.lon = degreesText(wrapLongitude(lon));
    placing.value = false;
  }

  /** Send the object as the form has it; a new one with no radio ticked goes on `start`. */
  function save(start: readonly RadioId[] = []): void {
    const command = objectCommand(draft, start);
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

  // An object that is gone is not selected.
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

  function move(name: string, lat: number, lon: number): void {
    const row = rows.get(name);
    if (row !== undefined) send(moveCommand(row, lat, lon));
  }

  function togglePlacing(): void {
    placing.value = !placing.value;
  }

  return reactive({ editing, placing, draft, dirty, picking, pin, edit, cancel, place, togglePlacing, save, kill, move });
}

export type OwnObjectsView = ReturnType<typeof useOwnObjects>;
