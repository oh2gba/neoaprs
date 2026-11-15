// The rows of a radio's waterfall (binary frames, lib/scoperow.ts) and what the page keeps of them, for the page's life and outside every pane (lib/scopememory.ts): the store hands it each row and the rows the daemon kept
// (`hfScopeHistory`, `hfScopeRow`), and it writes down every station heard on that radio as it is told, at the time the daemon wrote for it, so that a picture opened later has its calls where they were: the memory places
// it on this page's clock, with the SNR the radio measured of the frame where it was heard just now. A frame does not name its radio, so the page asks for one radio's rows at a time (composables/useScopeLooks.ts),
// and says here whose rows the memory holds (`rowsRadio`): the rows of another radio are let go when the page asks for that one's.
import { shallowRef, watch, type Ref } from "vue";
import type { RadioId } from "@/lib/radios";
import { HF_ID } from "@/lib/radiosides";
import { ScopeMemory } from "@/lib/scopememory";
import type { ScopeHistory, ScopeRow } from "@/lib/scoperow";
import type { PacketRow, TncState } from "@/protocol/protocol";

/** Whose rows each memory holds: null until the page's counting of who looks says it (and then the HF radio of before is taken, as the wire of before has it). */
const holders = new WeakMap<ScopeMemory, Ref<RadioId | null>>();

/** The radio whose rows the memory holds, for the counting of who looks to set; undefined for a memory this file did not make. */
export const rowsRadio = (memory: ScopeMemory): Ref<RadioId | null> | undefined => holders.get(memory);

/** A frame heard on that radio itself (not one from the internet, nor one of ours). */
const heardOn = (row: PacketRow, radio: RadioId | null): boolean =>
  (radio === null ? row.radio === "hf" : row.radio_id === radio) && row.direction === "in" && row.via !== "is";

export function useScopeRows(packets?: ReadonlyMap<string, PacketRow>, hf?: Readonly<Ref<TncState | null>>, clock?: () => number) {
  const memory = new ScopeMemory(clock);
  const radio = shallowRef<RadioId | null>(null);
  holders.set(memory, radio);
  // another radio's rows are asked for: what is held is not true of it (the rows the daemon kept of that one come after it)
  watch(
    radio,
    (now, was) => {
      if (was !== null && now !== was) memory.history({ rows: [], clock: (clock ?? Date.now)() });
    },
    { flush: "sync" },
  );
  if (packets) {
    let seen: number | null = null; // the newest packet written down; null before the page had any
    /** The newest packet's number: they count up in the order they came (in this run of the daemon). */
    const newest = (): number => {
      let id = 0;
      for (const row of packets.values()) id = Math.max(id, row.id);
      return id;
    };
    /** The SNR of the frame: for the HF radio of before the modem's of the latest frame, as the topic `hf` says it; for another radio the one the radio measured of the frame. */
    const snrOf = (row: PacketRow): number | null => (radio.value === null || radio.value === HF_ID ? (hf?.value?.modem?.snr ?? null) : row.snr);
    watch(
      newest,
      (id) => {
        if (id === 0) return;
        if (seen !== null && id < seen) return void (seen = id); // (the daemon was started again: its packets count from the start, and those it tells are written down already or older)
        const after = seen ?? 0;
        for (const row of [...packets.values()].filter((row) => row.id > after && heardOn(row, radio.value)).sort((a, b) => a.id - b.id))
          memory.hear(row.source, snrOf(row), Date.parse(row.heard_at));
        seen = id;
      },
      { immediate: true },
    );
  }
  return {
    memory,
    /** A row came: the store's `hfScopeRow`. */
    hfScopeRow: (row: ScopeRow): void => memory.live(row),
    /** The rows the daemon kept came: the store's `hfScopeHistory`. */
    hfScopeHistory: (history: ScopeHistory): void => memory.history(history),
  };
}
