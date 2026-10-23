// The Objects tab as the page runs it: the form of an object or an item of ours (open or not, a new one or the change of one the daemon has, the draft as it is typed), the place on the map that the form
// asks for (`placing`: a click on the map is the place, which `pin` shows meanwhile), and the commands that make, move and kill an object. The daemon holds the objects (the topic `own_objects`);
// the page only sends what the user did. A change opens the Objects tab, wherever it is asked for (the card of a station, a dragged marker does not need the form).
import { computed, reactive, ref, type Ref } from "vue";
import type { Panel } from "@/composables/usePanel";
import { draftOf, emptyDraft, moveCommand, objectCommand, wrapLongitude, type ObjectDraft } from "@/lib/ownobjects";
import type { Home } from "@/lib/mapview";
import { degreesText, parseNumber } from "@/lib/setup";
import type { Command, OwnObjectRow } from "@/protocol/protocol";

export function useOwnObjects(rows: ReadonlyMap<string, OwnObjectRow>, home: Ref<Home | null>, send: (command: Command) => boolean, panel: Panel) {
  const open = ref(false);
  const editing = ref<string | null>(null); // the name of the object that is being changed; null for a new one
  const placing = ref(false); // a click on the map is the place of the object
  const draft = reactive<ObjectDraft>(emptyDraft(null));

  const picking = computed(() => open.value && placing.value);
  const pin = computed(() => {
    const lat = parseNumber(draft.lat);
    const lon = parseNumber(draft.lon);
    return open.value && lat !== null && lon !== null && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? { lat, lon } : null;
  });

  /** The form for a new object, at the place we are. */
  function start(): void {
    Object.assign(draft, emptyDraft(home.value));
    editing.value = null;
    placing.value = false;
    open.value = true;
  }

  /** The form for the object of this name, with what the daemon has of it; the Objects tab in front. */
  function edit(name: string): void {
    const row = rows.get(name);
    if (row === undefined) return;
    Object.assign(draft, draftOf(row));
    editing.value = name;
    placing.value = false;
    open.value = true;
    panel.show("objects");
  }

  function cancel(): void {
    open.value = false;
    placing.value = false;
  }

  /** The place from a click on the map: five decimals (a metre). */
  function place(lat: number, lon: number): void {
    draft.lat = degreesText(Math.round(lat * 1e5) / 1e5);
    draft.lon = degreesText(wrapLongitude(lon));
    placing.value = false;
  }

  /** Sends the object as the form has it, and closes the form when it went. */
  function save(): void {
    const command = objectCommand(draft);
    if (command !== null && send(command)) cancel();
  }

  function kill(name: string): void {
    send({ cmd: "object_kill", name });
  }

  /** A marker was dragged: the object is where it was dropped. */
  function move(name: string, lat: number, lon: number): void {
    const row = rows.get(name);
    if (row !== undefined) send(moveCommand(row, lat, lon));
  }

  /** The Place button: the next click on the map is the place, or no longer. */
  function togglePlacing(): void {
    placing.value = !placing.value;
  }

  return reactive({ open, editing, placing, draft, picking, pin, start, edit, cancel, place, togglePlacing, save, kill, move });
}

export type OwnObjectsView = ReturnType<typeof useOwnObjects>;
