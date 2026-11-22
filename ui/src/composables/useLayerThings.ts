// The aircraft and ships as the page has them. The page looks at a layer (`layer_look` on) while the Layers box has its row (its source in force is not "none": the topic `map`), its tick is on, the page is in front, the
// socket is open and the map's replay is closed; when any of them goes it says so (off) and forgets the layer's table; and it looks again when the socket was opened anew, since the daemon forgets a page that left.
// The tables are the daemon's `layer_things`, the latest of each layer (`useLayerTables`, kept by the store of composables/useDaemon.ts as a radio's level is), and only those of the layers looked at count.
// Here too is the card of a thing that is open over the map (components/LayerCard.vue): one at a time, opened by a click on the thing, closed by its cross, Close all, Esc, a click on the map, and by itself
// when its thing has left the table. The way each thing has gone is kept here as the tables bring it (lib/layers/trail.ts: this page's own memory, begun with the look at the layer); the card's thing has its trail drawn. Nothing of it reaches the stations, the packets, the statistics or the replay.
import { computed, shallowRef, watch, type Ref } from "vue";
import { useMapLayers } from "@/composables/useMapLayers";
import type { Connection, Store } from "@/lib/hub";
import { keepList } from "@/lib/keeplist";
import type { LayerName, SourceName } from "@/lib/layers/sources";
import { growTrails, trailKey, type TrailPoint, type Trails } from "@/lib/layers/trail";
import { liveThings, type LayerTables } from "@/lib/layers/traffic";
import type { Command, LayerThing, MapState } from "@/protocol/protocol";

/** The layers of things, in the topic's order. */
const TRAFFIC_LAYERS: readonly LayerName[] = ["aircraft", "ships"];

/** The latest table of each layer the daemon told, and the way to forget one. */
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

/** The thing whose card is open, with its layer and the source its table came from. */
export interface OpenThing {
  layer: LayerName;
  thing: LayerThing;
  source: SourceName;
}

export interface LayerTraffic {
  /** the layers looked at now, in the topic's order */
  looked: Readonly<Ref<readonly LayerName[]>>;
  /** the table of each layer looked at */
  tables: Readonly<Ref<LayerTables>>;
  /** the thing whose card is open; null while none is */
  card: Readonly<Ref<OpenThing | null>>;
  /** The places the thing whose card is open has been seen at, the oldest first; none while no card is open. */
  trail: Readonly<Ref<readonly TrailPoint[]>>;
  /** Opens the card of that thing (in place of the one that is open). */
  open: (layer: LayerName, id: string) => void;
  /** Closes the card; whether one was open. */
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
  // at once (a socket that is closed says no to nothing: the daemon forgets the page by itself)
  watch(
    looked,
    (now, was = []) => {
      for (const layer of was.filter((one) => !now.includes(one))) {
        if (connection.value === "open") send({ cmd: "layer_look", layer, on: false });
        store.forget(layer);
      }
      for (const layer of now.filter((one) => !was.includes(one))) {
        store.forget(layer); // (a table that came late, after the last look ended, is not shown as this look's)
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
      if (now === null) opened.value = null; // (its thing left the table: the card does not come back with it)
    },
    { flush: "sync" },
  );
  // the trails of every thing looked at, grown as each table comes and forgotten with the thing and with the look
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
  // (the key is a plain string, so the trail does not change with the clock's tick that makes the card anew)
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
