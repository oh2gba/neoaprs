// Who looks at the lines put on APRS-IS, counted in one place (as in useRadioAsks): the Internet box
// of Settings says `look` while it is open and Send what I hear is on. The page asks the daemon for
// the lines (`igate_look`) while at least one pane looks, the page is in front and the socket is
// open; asked again when the socket was opened anew, as the daemon forgets a page that left.
import { computed, onBeforeUnmount, shallowRef, watch, type Ref } from "vue";
import type { Connection } from "@/lib/hub";
import type { Command } from "@/protocol/protocol";

export interface IgateLook {
  asked: Readonly<Ref<boolean>>;
  /** A pane, from its setup on: it looks while `looking` is true and stops when it goes. */
  look: (looking: () => boolean) => void;
}

export function useIgateLook(
  send: (command: Command) => boolean,
  connection: Readonly<Ref<Connection>>,
  visible: Readonly<Ref<boolean>>,
): IgateLook {
  const looking = shallowRef<readonly (() => boolean)[]>([]);
  const asked = computed(() => visible.value && connection.value === "open" && looking.value.length > 0);
  // At once, not on the next tick: a pane that looks from its first moment asks in that moment. A
  // closed socket says no to nothing: the daemon forgets the page by itself.
  watch(
    asked,
    (now, was) => {
      if (now) send({ cmd: "igate_look", on: true });
      else if (was && connection.value === "open") send({ cmd: "igate_look", on: false });
    },
    { flush: "sync" },
  );

  function look(looks: () => boolean): void {
    let now = false;
    const set = (on: boolean): void => {
      if (on === now) return;
      now = on;
      looking.value = on ? [...looking.value, looks] : looking.value.filter((other) => other !== looks);
    };
    const stop = watch(looks, set, { immediate: true, flush: "sync" });
    onBeforeUnmount(() => {
      stop();
      set(false);
    });
  }
  return { asked, look };
}
