// The rows of the HF radio's waterfall (binary frames, lib/scoperow.ts) and what the page keeps of them, for the page's life and outside every pane (lib/scopememory.ts): the store hands it each row and the rows the daemon kept
// (`hfScopeHistory`, `hfScopeRow`), and it writes down every station heard on the HF radio as it is told, at the time the daemon wrote for it, so that a picture opened later has its calls where they were: the memory places
// it on this page's clock, with the modem's SNR where it was heard just now.
import { watch, type Ref } from "vue";
import { ScopeMemory } from "@/lib/scopememory";
import type { ScopeHistory, ScopeRow } from "@/lib/scoperow";
import type { PacketRow, TncState } from "@/protocol/protocol";

/** A frame heard on the HF radio itself (not one from the internet, nor one of ours). */
const heardOnHf = (row: PacketRow): boolean => row.radio === "hf" && row.direction === "in" && row.via !== "is";

export function useScopeRows(packets?: ReadonlyMap<string, PacketRow>, hf?: Readonly<Ref<TncState | null>>, clock?: () => number) {
  const memory = new ScopeMemory(clock);
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
        const snr = hf?.value?.modem?.snr ?? null;
        for (const row of [...packets.values()].filter((row) => row.id > after && heardOnHf(row)).sort((a, b) => a.id - b.id))
          memory.hear(row.source, snr, Date.parse(row.heard_at));
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
