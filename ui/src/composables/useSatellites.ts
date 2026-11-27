// The satellites layer as the page has it. The page looks (`satellite_look` on, with the ids of its
// open cards) while the tick of Satellites is on, the page is in front, the socket is open and the
// map's replay is closed, and says so again whenever a card opens or closes; when any of these goes
// it says off and forgets what it was told, and it looks again when the socket was opened anew,
// since the daemon forgets a page that left. Any number of cards may be open, oldest first; a card
// closes by its cross, Close all or Esc (the newest first), when the tick goes off, or when its
// satellite is no longer shown. While the page looks a clock of its own moves every second, so the
// marks, the time left and the Doppler move smoothly between what the daemon sent.
import { computed, getCurrentScope, onScopeDispose, ref, shallowRef, watch, type Ref } from "vue";
import { useMapLayers } from "@/composables/useMapLayers";
import type { Connection, Store } from "@/lib/hub";
import type { Command, MapState, SatelliteCard, SatellitesMessage } from "@/protocol/protocol";

const TICK_MS = 1000;

export function useSatelliteStore() {
  const told = shallowRef<SatellitesMessage | null>(null);
  const handlers: Pick<Store, "satellites"> = { satellites: (message) => (told.value = message) };
  return { told, forget: () => void (told.value = null), handlers };
}

type SatelliteStore = Pick<ReturnType<typeof useSatelliteStore>, "told" | "forget">;

export interface SatelliteLayer {
  looked: Readonly<Ref<boolean>>;
  told: Readonly<Ref<SatellitesMessage | null>>;
  /** The open cards, oldest first: those the daemon has told. */
  cards: Readonly<Ref<readonly SatelliteCard[]>>;
  /** The ids of the open cards, a card the daemon has not told yet among them. */
  opened: Readonly<Ref<readonly number[]>>;
  now: Readonly<Ref<number>>;
  /** Open a satellite's card; `alone` closes the others first (a phone has one card). */
  open: (id: number, alone?: boolean) => void;
  closeCard: (id: number) => void;
  /** Close the newest card: true if one was open. */
  close: () => boolean;
  closeAll: () => boolean;
}

export interface SatelliteParts {
  send: (command: Command) => boolean;
  connection: Readonly<Ref<Connection>>;
  visible: Readonly<Ref<boolean>>;
  replay: Readonly<Ref<boolean>>;
  map: Readonly<Ref<MapState | null>>;
  store: SatelliteStore;
}

export function useSatellites(parts: SatelliteParts): SatelliteLayer {
  const { send, connection, store } = parts;
  const ticks = useMapLayers(parts.map);
  const ticked = computed(() => ticks.ticked("satellites"));
  const looked = computed(
    () => ticked.value && parts.visible.value && connection.value === "open" && !parts.replay.value,
  );
  const opened = ref<number[]>([]);
  const now = ref(Date.now());
  let timer: ReturnType<typeof setInterval> | undefined;

  watch(
    ticked,
    (on) => {
      if (!on) opened.value = [];
    },
    { flush: "sync" },
  );
  // One command for the look and its cards, sent again as either changes.
  watch(
    [looked, () => opened.value.join(" ")],
    ([on], [was]) => {
      if (on) send({ cmd: "satellite_look", on: true, cards: [...opened.value] });
      else if (was) {
        if (connection.value === "open") send({ cmd: "satellite_look", on: false, cards: [] });
        store.forget();
      }
      clearInterval(timer);
      timer = undefined;
      if (on) {
        now.value = Date.now();
        timer = setInterval(() => (now.value = Date.now()), TICK_MS);
      }
    },
    { flush: "sync", immediate: true },
  );
  if (getCurrentScope()) onScopeDispose(() => clearInterval(timer));

  const told = computed(() => (looked.value ? store.told.value : null));
  // A card whose satellite is no longer shown closes.
  watch(
    told,
    (message) => {
      if (message === null) return;
      const shown = new Set(message.satellites.map((one) => one.id));
      if (opened.value.some((id) => !shown.has(id))) opened.value = opened.value.filter((id) => shown.has(id));
    },
    { flush: "sync" },
  );
  const cards = computed<readonly SatelliteCard[]>(() => {
    const message = told.value;
    if (message === null) return [];
    return opened.value.flatMap((id) => message.cards.filter((card) => card.id === id));
  });

  const closeCard = (id: number): void => void (opened.value = opened.value.filter((one) => one !== id));
  return {
    looked,
    told,
    cards,
    opened,
    now,
    open: (id, alone = false) => {
      if (alone) opened.value = [id];
      else if (!opened.value.includes(id)) opened.value = [...opened.value, id];
    },
    closeCard,
    close: () => {
      const last = opened.value.at(-1);
      if (last === undefined) return false;
      closeCard(last);
      return true;
    },
    closeAll: () => {
      const was = opened.value.length > 0;
      opened.value = [];
      return was;
    },
  };
}
