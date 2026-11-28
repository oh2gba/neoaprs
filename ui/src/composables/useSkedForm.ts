// What Plan a test holds while the Skeds tab is there, so that a dialog closed without posting opens
// again as it was: the draft (lib/skeds.ts), the days to choose from, the suggested dials, and the
// ask for a fresh list of dials (`frequencies`), at most once a minute and, when the socket is not
// open yet, as soon as it opens. Join fills it with a test of the board.
import { computed, reactive, watch } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { OTHER_DIAL, dayChoices, numberOfDial, startDraft, utcDay, type SkedGroup } from "@/lib/skeds";

const ASK_EVERY_MS = 60_000;

export function useSkedForm() {
  const { skeds, now, send, connection } = useDaemonContext();
  const frequencies = computed(() => skeds.value?.frequencies ?? []);
  const draft = reactive(startDraft(now.value, frequencies.value));
  const days = computed(() => dayChoices(now.value));
  /** Whether a dial was chosen or filled: the first suggested one stands in until then. */
  let chosen = false;

  watch(days, (list) => {
    if (!list.some((d) => d.value === draft.day)) draft.day = utcDay(now.value);
  });
  watch(frequencies, (list) => {
    if (chosen || list[0] === undefined) return;
    draft.typed = false;
    draft.dial = list[0].dial;
  });

  function choose(value: string): void {
    chosen = true;
    draft.typed = value === OTHER_DIAL;
    draft.dial = value === OTHER_DIAL ? "" : value;
  }

  /** The day, the times and the dial of a test of the board; a dial not suggested is Other's number. */
  function fill(group: SkedGroup): void {
    const from = Date.parse(group.from);
    const clock = (iso: string): string => new Date(Date.parse(iso)).toISOString().slice(11, 16);
    chosen = true;
    draft.day = utcDay(from);
    draft.from = clock(group.from);
    draft.to = clock(group.to);
    draft.typed = !frequencies.value.some((f) => f.dial === group.dial);
    draft.dial = draft.typed ? numberOfDial(group.dial) : group.dial;
  }

  let asked = Number.NEGATIVE_INFINITY;
  let missed = false;
  function refresh(): void {
    if (connection.value !== "open") {
      missed = true;
      return;
    }
    const at = Date.now();
    if (at - asked < ASK_EVERY_MS) return;
    asked = at;
    send({ cmd: "frequencies" });
  }
  watch(connection, (state) => {
    if (state !== "open" || !missed) return;
    missed = false;
    refresh();
  });

  return { draft, days, frequencies, choose, fill, refresh };
}

export type SkedForm = ReturnType<typeof useSkedForm>;
