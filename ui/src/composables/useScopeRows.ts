// The rows of each radio's waterfall (binary frames that name their radio, lib/scoperow.ts) and what the page keeps of them, a memory for each radio, for the page's life and outside every pane (lib/scopememory.ts): the store
// hands it each row and the rows the daemon kept with the radio they are of (`hfScopeHistory`, `hfScopeRow`), and it writes down every station heard on a radio whose rows it keeps as it is told, at the time the daemon wrote
// for it, so that a picture opened later has its calls where they were: the memory places it on this page's clock, with the SNR the radio measured of the frame where it was heard just now. Radio 2's memory (the HF radio
// of before) is there from the start; another radio's is made when a pane first shows that radio or its first rows come.
import { watch, type Ref } from "vue";
import type { RadioId } from "@/lib/radios";
import { HF_ID } from "@/lib/radiosides";
import { ScopeMemory } from "@/lib/scopememory";
import type { ScopeHistory, ScopeRow } from "@/lib/scoperow";
import type { PacketRow, TncState } from "@/protocol/protocol";

/** The radio a frame was heard on itself (not one from the internet, nor one of ours); null for none. A packet of before names its radio by its word alone: the HF radio's is radio 2's. */
const heardOn = (row: PacketRow): RadioId | null => (row.direction !== "in" || row.via === "is" ? null : (row.radio_id ?? (row.radio === "hf" ? HF_ID : null)));

/** The memory of each radio's rows, made the first time it is asked for: `seed` is radio 2's (a test's own, or a new one). */
export function scopeMemories(seed: ScopeMemory, clock?: () => number): { of: (radio: RadioId) => ScopeMemory; has: (radio: RadioId) => boolean } {
  const memories = new Map<RadioId, ScopeMemory>([[HF_ID, seed]]);
  return {
    of: (radio) => {
      let memory = memories.get(radio);
      if (memory === undefined) {
        memory = new ScopeMemory(clock);
        memories.set(radio, memory);
      }
      return memory;
    },
    has: (radio) => memories.has(radio),
  };
}

export function useScopeRows(packets?: ReadonlyMap<string, PacketRow>, hf?: Readonly<Ref<TncState | null>>, clock?: () => number) {
  const memory = new ScopeMemory(clock);
  const memories = scopeMemories(memory, clock);
  if (packets) {
    let seen: number | null = null; // the newest packet written down; null before the page had any
    /** The newest packet's number: they count up in the order they came (in this run of the daemon). */
    const newest = (): number => {
      let id = 0;
      for (const row of packets.values()) id = Math.max(id, row.id);
      return id;
    };
    /** The SNR of the frame: for the HF radio of before the modem's of the latest frame, as the topic `hf` says it; for another radio the one the radio measured of the frame. */
    const snrOf = (row: PacketRow, radio: RadioId): number | null => (radio === HF_ID ? (hf?.value?.modem?.snr ?? null) : row.snr);
    watch(
      newest,
      (id) => {
        if (id === 0) return;
        if (seen !== null && id < seen) return void (seen = id); // (the daemon was started again: its packets count from the start, and those it tells are written down already or older)
        const after = seen ?? 0;
        for (const row of [...packets.values()].filter((row) => row.id > after).sort((a, b) => a.id - b.id)) {
          const radio = heardOn(row);
          if (radio !== null && memories.has(radio)) memories.of(radio).hear(row.source, snrOf(row, radio), Date.parse(row.heard_at));
        }
        seen = id;
      },
      { immediate: true },
    );
  }
  return {
    /** radio 2's memory (the HF radio of before) */
    memory,
    /** the memory of a radio's rows */
    of: memories.of,
    /** A row came: the store's `hfScopeRow`. */
    hfScopeRow: (row: ScopeRow, radio: RadioId = HF_ID): void => memories.of(radio).live(row),
    /** The rows the daemon kept came: the store's `hfScopeHistory`. */
    hfScopeHistory: (history: ScopeHistory, radio: RadioId = HF_ID): void => memories.of(radio).history(history),
  };
}
