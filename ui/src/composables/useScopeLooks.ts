// Who is looking at the HF radio's scope, counted in one place: the box in Settings (composables/useHfScope.ts) and the monitor card over the map (components/MonitorCard.vue) each say `look` while they show the picture, and the page asks
// the daemon for the rows (`hf_scope`) while at least one does, this page is in front, the modem has the interface that makes them (`modem.scope`) and the socket is open; asked again when the socket was open anew, since the daemon forgets a page
// that left. Nobody looking, no rows.
import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import type { Connection } from "@/lib/hub";
import type { Command, TncState } from "@/protocol/protocol";

export interface ScopeLooks {
  /** the modem has the interface that makes the rows: there is a scope to show */
  available: Readonly<Ref<boolean>>;
  /** the rows are asked for: someone looks, the page is in front and the socket is open */
  wanted: Readonly<Ref<boolean>>;
  /** how many panes are looking now */
  lookers: Readonly<Ref<number>>;
  /** A pane, from its setup on: it looks while `looking` is true and stops when it goes. */
  look: (looking: () => boolean) => void;
}

export function useScopeLooks(
  send: (command: Command) => boolean,
  hf: Readonly<Ref<TncState | null>>,
  connection: Readonly<Ref<Connection>>,
  visible: Readonly<Ref<boolean>>,
): ScopeLooks {
  const lookers = ref(0);
  const available = computed(() => hf.value?.modem?.scope === true);
  const wanted = computed(() => lookers.value > 0 && visible.value && available.value && connection.value === "open");
  // at once, not on the next tick: a pane that looks from its first moment asks in that moment
  // (a socket that is closed says no to nothing: the daemon forgets the page by itself)
  watch(wanted, (on) => (on || connection.value === "open") && void send({ cmd: "hf_scope", on }), { flush: "sync" });

  function look(looking: () => boolean): void {
    let now = false;
    const stop = watch(
      looking,
      (on) => {
        if (on === now) return;
        now = on;
        lookers.value += on ? 1 : -1;
      },
      { immediate: true, flush: "sync" },
    );
    onBeforeUnmount(() => {
      stop();
      if (now) lookers.value -= 1;
      now = false;
    });
  }
  return { available, wanted, lookers, look };
}
