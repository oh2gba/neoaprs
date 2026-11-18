// The map's layers as this browser has them: the rows the Layers box lists now (lib/layers/table.ts, from the topic `map`'s `layers`) and each row's tick, which is this browser's own (kept as `layer.<id>`, "on" or "off",
// Tracks and the ALOHA circle on out of the box, the rest off), so that a phone and the desktop can show different things. The ticks are one set for the whole page: the box, the map and the layers of things read the same.
import { computed, effectScope, type ComputedRef, type EffectScope, type Ref, type WritableComputedRef } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { usePersistedFlag } from "@/composables/usePersisted";
import { LAYER_TABLE, layerRows, type LayerId, type LayerRow } from "@/lib/layers/table";
import type { MapState } from "@/protocol/protocol";

type Ticks = Readonly<Record<LayerId, WritableComputedRef<boolean>>>;

let scope: EffectScope | null = null;
let ticks: Ticks | null = null;

/** The page's one set of ticks, read from this browser's memory the first time it is asked for. */
function pageTicks(): Ticks {
  if (ticks) return ticks;
  scope = effectScope(true);
  ticks =
    scope.run(() => Object.fromEntries(LAYER_TABLE.map((row) => [row.id, usePersistedFlag(`layer.${row.id}`, ["on", "off"], row.tick)])) as Ticks) ?? null;
  if (!ticks) throw new Error("the ticks of the layers were not made");
  return ticks;
}

/** Forgets the ticks, so that they are read from this browser's memory again, as after a reload (for the tests). */
export function forgetLayerTicks(): void {
  scope?.stop();
  scope = null;
  ticks = null;
}

export interface MapLayers {
  /** the rows to draw now */
  rows: ComputedRef<LayerRow[]>;
  ticked: (id: LayerId) => boolean;
  setTicked: (id: LayerId, on: boolean) => void;
}

/** The rows of the topic `map` the page has (the page's context unless the page itself gives it: composables/useAppShell.ts, which provides the context). */
export function useMapLayers(map?: Readonly<Ref<MapState | null>>): MapLayers {
  const topic = map ?? useDaemonContext().map;
  const own = pageTicks();
  return {
    rows: computed(() => layerRows(topic.value?.layers)),
    ticked: (id) => own[id].value,
    setTicked: (id, on) => (own[id].value = on),
  };
}
