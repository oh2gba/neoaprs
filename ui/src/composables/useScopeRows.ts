// The rows of each radio's waterfall (binary frames that name their radio, lib/scoperow.ts) and what the page keeps of them, a memory for each radio, for the page's life and outside every pane (lib/scopememory.ts): the store
// hands it each row and the rows the daemon kept with the radio they are of (`hfScopeHistory`, `hfScopeRow`), and it writes down every station heard on a radio whose rows it keeps as it is told, at the time the daemon wrote
// for it, so that a picture opened later has its calls where they were: the memory places it on this page's clock, with the SNR the radio measured of the frame where it was heard just now. A radio's memory is made when a
// pane first shows that radio, its first rows come or a station is first heard on it.
import { watch } from "vue";
import type { RadioId } from "@/lib/radios";
import { ScopeMemory } from "@/lib/scopememory";
import type { ScopeHistory, ScopeRow } from "@/lib/scoperow";
import type { PacketRow } from "@/protocol/protocol";

/** The radio a frame was heard on itself (not one from the internet, nor one of ours); null for none. */
const heardOn = (row: PacketRow): RadioId | null => (row.direction !== "in" || row.via === "is" ? null : row.radio_id);

/** The memory of each radio's rows, made the first time it is asked for. */
export function scopeMemories(clock?: () => number): { of: (radio: RadioId) => ScopeMemory } {
  const memories = new Map<RadioId, ScopeMemory>();
  return {
    of: (radio) => {
      let memory = memories.get(radio);
      if (memory === undefined) {
        memory = new ScopeMemory(clock);
        memories.set(radio, memory);
      }
      return memory;
    },
  };
}

export function useScopeRows(packets?: ReadonlyMap<string, PacketRow>, clock?: () => number) {
  const memories = scopeMemories(clock);
  if (packets) {
    let seen: number | null = null; // the newest packet written down; null before the page had any
    /** The newest packet's number: they count up in the order they came (in this run of the daemon). */
    const newest = (): number => {
      let id = 0;
      for (const row of packets.values()) id = Math.max(id, row.id);
      return id;
    };
    watch(
      newest,
      (id) => {
        if (id === 0) return;
        if (seen !== null && id < seen) return void (seen = id); // (the daemon was started again: its packets count from the start, and those it tells are written down already or older)
        const after = seen ?? 0;
        for (const row of [...packets.values()].filter((row) => row.id > after).sort((a, b) => a.id - b.id)) {
          const radio = heardOn(row);
          if (radio !== null) memories.of(radio).hear(row.source, row.snr, Date.parse(row.heard_at)); // (the SNR the radio measured of the frame)
        }
        seen = id;
      },
      { immediate: true },
    );
  }
  return {
    /** the memory of a radio's rows */
    of: memories.of,
    /** A row of that radio came: the store's `hfScopeRow`. */
    hfScopeRow: (row: ScopeRow, radio: RadioId): void => memories.of(radio).live(row),
    /** The rows the daemon kept of that radio came: the store's `hfScopeHistory`. */
    hfScopeHistory: (history: ScopeHistory, radio: RadioId): void => memories.of(radio).history(history),
  };
}
