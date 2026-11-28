// Who looks at something the daemon sends only while asked (a radio's scope `radio_scope`, a Sound
// card radio's receive level `radio_level`), counted in one place: each pane says `look` while it
// shows it, and of which radio. The page asks the daemon for that radio (`{ cmd, radio, on: true
// }`) while at least one pane looks, the page is in front, the radio can have it (`offered`) and
// the socket is open; asked again when the socket was opened anew, as the daemon forgets a page
// that left. Each radio is asked for and stopped on its own, at once. A pane may say how many
// seconds it wants (the scope's history): the radio is asked for the most of its panes', and asked
// again when that changes.
import { computed, onBeforeUnmount, shallowRef, watch, type Ref } from "vue";
import type { Connection } from "@/lib/hub";
import { keepList } from "@/lib/keeplist";
import type { RadioId } from "@/lib/radios";
import type { Command } from "@/protocol/protocol";

export interface RadioAsks {
  asked: Readonly<Ref<readonly RadioId[]>>;
  /** The seconds asked for each radio asked whose panes say how many. */
  seconds: Readonly<Ref<ReadonlyMap<RadioId, number>>>;
  lookers: Readonly<Ref<number>>;
  /**
   * A pane, from its setup on: it looks at `radio` while `looking` is true and stops when it goes;
   * `seconds`, if given, is how many it wants (undefined: none said).
   */
  look: (looking: () => boolean, radio: () => RadioId | null, seconds?: () => number | undefined) => void;
}

interface Pane {
  radio: () => RadioId | null;
  seconds?: () => number | undefined;
}

export function useRadioAsks(
  cmd: "radio_scope" | "radio_level",
  send: (command: Command) => boolean,
  connection: Readonly<Ref<Connection>>,
  visible: Readonly<Ref<boolean>>,
  offered: () => readonly RadioId[] | null,
): RadioAsks {
  const looking = shallowRef<readonly Pane[]>([]);
  const asked = computed<readonly RadioId[]>((old) => {
    const wanted = visible.value && connection.value === "open" ? looking.value.map((pane) => pane.radio()) : [];
    const ids = (
      offered() ?? [...new Set(wanted)].filter((id): id is RadioId => id !== null).sort((a, b) => a - b)
    ).filter((radio) => wanted.includes(radio));
    return keepList(old, ids);
  });
  const seconds = computed<ReadonlyMap<RadioId, number>>(() => {
    const most = new Map<RadioId, number>();
    for (const pane of looking.value) {
      const [radio, wants] = [pane.radio(), pane.seconds?.()];
      if (radio !== null && wants !== undefined && asked.value.includes(radio))
        most.set(radio, Math.max(wants, most.get(radio) ?? 0));
    }
    return most;
  });
  const ask = (radio: RadioId, wants: number | undefined): boolean =>
    send(
      cmd === "radio_scope" && wants !== undefined
        ? { cmd, radio, on: true, seconds: wants }
        : { cmd, radio, on: true },
    );
  // At once, not on the next tick: a pane that looks from its first moment asks in that moment. A
  // closed socket says no to nothing: the daemon forgets the page by itself.
  watch(
    [asked, seconds],
    ([now, wants], [was = [], wanted]) => {
      if (connection.value === "open")
        for (const radio of was.filter((id) => !now.includes(id))) send({ cmd, radio, on: false });
      for (const radio of now)
        if (!was.includes(radio) || wants.get(radio) !== wanted?.get(radio)) ask(radio, wants.get(radio));
    },
    { flush: "sync" },
  );

  function look(looks: () => boolean, radio: () => RadioId | null, wants?: () => number | undefined): void {
    const pane: Pane = { radio: () => radio(), seconds: wants };
    let now = false;
    const set = (on: boolean): void => {
      if (on === now) return;
      now = on;
      looking.value = on ? [...looking.value, pane] : looking.value.filter((other) => other !== pane);
    };
    const stop = watch(looks, set, { immediate: true, flush: "sync" });
    onBeforeUnmount(() => {
      stop();
      set(false);
    });
  }
  return { asked, seconds, lookers: computed(() => looking.value.length), look };
}
