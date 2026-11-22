// The rows of each radio's waterfall (binary frames naming their radio, lib/scoperow.ts) and what
// the page keeps of them: a memory per radio for the page's life, outside every pane
// (lib/scopememory.ts). The store hands it each row and the rows the daemon kept (`hfScopeHistory`,
// `hfScopeRow`); it also records each station heard on a radio whose rows it keeps, at the time the
// daemon wrote, so that a picture opened later has its calls where they were. A radio's memory is
// made when a pane first shows it, its first rows come or a station is first heard on it.
import { watch } from "vue";
import type { RadioId } from "@/lib/radios";
import { ScopeMemory } from "@/lib/scopememory";
import type { ScopeHistory, ScopeRow } from "@/lib/scoperow";
import type { PacketRow } from "@/protocol/protocol";

/** The radio a frame was heard on itself (not from the internet, not ours); null for none. */
const heardOn = (row: PacketRow): RadioId | null => (row.direction !== "in" || row.via === "is" ? null : row.radio_id);

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
    let seen: number | null = null;
    /**
     * The newest packet's number: they count up in the order they came (in this run of the daemon).
     */
    const newest = (): number => {
      let id = 0;
      for (const row of packets.values()) id = Math.max(id, row.id);
      return id;
    };
    watch(
      newest,
      (id) => {
        if (id === 0) return;
        // After a daemon restart its packet ids count from the start, and those it sends are
        // written down already or older.
        if (seen !== null && id < seen) return void (seen = id);
        const after = seen ?? 0;
        for (const row of [...packets.values()].filter((row) => row.id > after).sort((a, b) => a.id - b.id)) {
          const radio = heardOn(row);
          if (radio !== null) memories.of(radio).hear(row.source, row.snr, Date.parse(row.heard_at));
        }
        seen = id;
      },
      { immediate: true },
    );
  }
  return {
    of: memories.of,
    hfScopeRow: (row: ScopeRow, radio: RadioId): void => memories.of(radio).live(row),
    hfScopeHistory: (history: ScopeHistory, radio: RadioId): void => memories.of(radio).history(history),
  };
}
