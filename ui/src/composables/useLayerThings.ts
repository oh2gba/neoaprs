// The aircraft and ships as the page has them. The page looks at a layer (`layer_look` on) while
// the Layers box has its row (its source is not "none"), its tick is on, the page is in front,
// the socket is open and the map's replay is closed; when any of these goes it says so (off) and
// forgets the layer's table, and it looks again when the socket was opened anew, since the daemon
// forgets a page that left. The tables are the daemon's `layer_things`, the latest of each layer
// (`useLayerTables`); only those of the layers looked at count. The card of a thing open over the
// map is here too: one at a time, closed by its cross, Close all, Esc, a click on the map, or when
// its thing leaves the table. The way each thing has gone is kept as the tables bring it
// (lib/layers/trail.ts, begun with the look at the layer); the card's thing has its trail drawn.
// None of it reaches the stations, packets, statistics or the replay.
import { computed, shallowRef, watch, type Ref } from "vue";
import { useMapLayers } from "@/composables/useMapLayers";
import type { Connection, Store } from "@/lib/hub";
import { keepList } from "@/lib/keeplist";
import type { LayerName, SourceName } from "@/lib/layers/sources";
import { growTrails, trailKey, type TrailPoint, type Trails } from "@/lib/layers/trail";
import { liveThings, type LayerTables } from "@/lib/layers/traffic";
import type { Command, LayerThing, MapState } from "@/protocol/protocol";

const TRAFFIC_LAYERS: readonly LayerName[] = ["aircraft", "ships"];

export function useLayerTables() {
  const told = shallowRef<LayerTables>(new Map());
  const handlers: Pick<Store, "layerThings"> = { layerThings: (message) => (told.value = new Map(told.value).set(message.layer, message)) };
  function forget(layer: LayerName): void {
    if (!told.value.has(layer)) return;
    const next = new Map(told.value);
    next.delete(layer);
    told.value = next;
  }
  return { told, forget, handlers };
}

type LayerTableStore = Pick<ReturnType<typeof useLayerTables>, "told" | "forget">;

export interface OpenThing {
  layer: LayerName;
  thing: LayerThing;
  source: SourceName;
}

export interface LayerTraffic {
  looked: Readonly<Ref<readonly LayerName[]>>;
  tables: Readonly<Ref<LayerTables>>;
  card: Readonly<Ref<OpenThing | null>>;
  trail: Readonly<Ref<readonly TrailPoint[]>>;
  open: (layer: LayerName, id: string) => void;
  close: () => boolean;
}

export interface TrafficParts {
  send: (command: Command) => boolean;
  connection: Readonly<Ref<Connection>>;
  visible: Readonly<Ref<boolean>>;
  replay: Readonly<Ref<boolean>>;
  map: Readonly<Ref<MapState | null>>;
  now: Readonly<Ref<number>>;
  store: LayerTableStore;
}

export function useLayerThings(parts: TrafficParts): LayerTraffic {
  const { send, connection, store } = parts;
  const ticks = useMapLayers(parts.map);
  const looked = computed<readonly LayerName[]>((old) => {
    const front = parts.visible.value && connection.value === "open" && !parts.replay.value;
    const rows = ticks.rows.value;
    const layers = front ? TRAFFIC_LAYERS.filter((layer) => rows.some((row) => row.id === layer) && ticks.ticked(layer)) : [];
    return keepList(old, layers);
  });
  // A closed socket says no to nothing: the daemon forgets the page by itself.
  watch(
    looked,
    (now, was = []) => {
      for (const layer of was.filter((one) => !now.includes(one))) {
        if (connection.value === "open") send({ cmd: "layer_look", layer, on: false });
        store.forget(layer);
      }
      for (const layer of now.filter((one) => !was.includes(one))) {
        store.forget(layer);
        send({ cmd: "layer_look", layer, on: true });
      }
    },
    { flush: "sync", immediate: true },
  );
  const tables = computed<LayerTables>(() => new Map([...store.told.value].filter(([layer]) => looked.value.includes(layer))));

  const opened = shallowRef<{ layer: LayerName; id: string } | null>(null);
  const find = (layer: LayerName, id: string): OpenThing | null => {
    const table = tables.value.get(layer);
    const thing = table ? liveThings(table, parts.now.value).find((one) => one.id === id) : undefined;
    return table && thing ? { layer, thing, source: table.source } : null;
  };
  const card = computed(() => (opened.value ? find(opened.value.layer, opened.value.id) : null));
  watch(
    card,
    (now) => {
      if (now === null) opened.value = null;
    },
    { flush: "sync" },
  );
  // The trails of every thing looked at, grown as each table comes, forgotten with the thing and
  // the look.
  const trails: Trails = new Map();
  const grown = shallowRef(0);
  watch(
    tables,
    (now) => {
      growTrails(trails, now.values(), parts.now.value);
      grown.value++;
    },
    { flush: "sync" },
  );
  // The key is a plain string, so the trail does not change with the clock tick that remakes the
  // card.
  const openKey = computed(() => (card.value ? trailKey(card.value.layer, card.value.thing.id) : null));
  const trail = computed<readonly TrailPoint[]>(() => {
    void grown.value;
    return openKey.value ? [...(trails.get(openKey.value) ?? [])] : [];
  });
  return {
    looked,
    tables,
    card,
    trail,
    open: (layer, id) => void (opened.value = find(layer, id) ? { layer, id } : null),
    close: () => {
      const was = opened.value !== null;
      opened.value = null;
      return was;
    },
  };
}
