// The map's layers as this browser has them: the rows of the Layers box (from the topic `map`)
// and each row's tick, kept per browser as `layer.<id>` ("on" or "off"; Tracks and the ALOHA
// circle are on by default), so that a phone and the desktop can differ. The ticks are one set
// for the page.
import { computed, effectScope, type ComputedRef, type EffectScope, type Ref, type WritableComputedRef } from "vue";
import { useDaemonContext } from "@/composables/useDaemonContext";
import { usePersistedFlag } from "@/composables/usePersisted";
import { useRadios } from "@/composables/useRadios";
import { LAYER_TABLE, layerRows, type LayerId, type LayerRow } from "@/lib/layers/table";
import type { MapState } from "@/protocol/protocol";

type Ticks = Readonly<Record<LayerId, WritableComputedRef<boolean>>>;

let scope: EffectScope | null = null;
let ticks: Ticks | null = null;

function pageTicks(): Ticks {
  if (ticks) return ticks;
  scope = effectScope(true);
  ticks =
    scope.run(
      () =>
        Object.fromEntries(
          LAYER_TABLE.map((row) => [row.id, usePersistedFlag(`layer.${row.id}`, ["on", "off"], row.tick)]),
        ) as Ticks,
    ) ?? null;
  if (!ticks) throw new Error("the ticks of the layers were not made");
  return ticks;
}

/** Forget the ticks so that they are read from storage again (for the tests). */
export function forgetLayerTicks(): void {
  scope?.stop();
  scope = null;
  ticks = null;
}

export interface MapLayers {
  rows: ComputedRef<LayerRow[]>;
  /** Whether the row is listed now. */
  shown: (id: LayerId) => boolean;
  ticked: (id: LayerId) => boolean;
  setTicked: (id: LayerId, on: boolean) => void;
}

export function useMapLayers(map?: Readonly<Ref<MapState | null>>, hf?: () => boolean): MapLayers {
  const topic = map ?? useDaemonContext().map;
  const radios = hf ? null : useRadios();
  const hasHf = hf ?? (() => radios?.enabled.value.some((radio) => radio.kind === "hf") ?? false);
  const own = pageTicks();
  const rows = computed(() => layerRows(topic.value?.layers, hasHf()));
  return {
    rows,
    shown: (id) => rows.value.some((row) => row.id === id),
    ticked: (id) => own[id].value,
    setTicked: (id, on) => (own[id].value = on),
  };
}
