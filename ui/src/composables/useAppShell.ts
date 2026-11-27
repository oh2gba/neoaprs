// The page put together (App.vue is its layout): the daemon, the clock, the settings, the
// first-run guide, the panel, the tab models, the station cards, the statistics card, the map
// replay, the aircraft and ships layers and the places picked on the map, with what the shell
// itself decides: ports are asked for each time the daemon connects, the guide opens once by
// itself when the daemon has no call, the update steps are open on purpose and go with the newer
// version, the notes of the running version open from Settings and from the line shown once
// after an update, and the header mail opens the tab with unseen messages. What the panes share
// is provided (`useDaemonContext`); what only the layout needs is returned.
import { computed, ref, watch, type Ref, type WritableComputedRef } from "vue";
import { provideDaemon } from "@/composables/useDaemonContext";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { useBulletins } from "@/composables/useBulletins";
import { useDaemon } from "@/composables/useDaemon";
import { useDark } from "@/composables/useDark";
import { useElementWidth } from "@/composables/useElementWidth";
import { useEmail } from "@/composables/useEmail";
import { useFindRadio } from "@/composables/useFindRadio";
import { useFormEsc } from "@/composables/useFormEsc";
import { useHeardIndex } from "@/composables/useHeardIndex";
import { useHome } from "@/composables/useHome";
import { useLayerThings } from "@/composables/useLayerThings";
import { useSatellites } from "@/composables/useSatellites";
import { useLayout } from "@/composables/useLayout";
import { useMapPicks } from "@/composables/useMapPicks";
import { useMessagesView } from "@/composables/useMessagesView";
import { useNotice } from "@/composables/useNotice";
import { useNow } from "@/composables/useNow";
import { useOwnObjects } from "@/composables/useOwnObjects";
import { usePersistedFlag } from "@/composables/usePersisted";
import { usePageAlerts } from "@/composables/usePageAlerts";
import { usePanel } from "@/composables/usePanel";
import { useRadioAsks } from "@/composables/useRadioAsks";
import { useScopeLooks } from "@/composables/useScopeLooks";
import { useSettings } from "@/composables/useSettings";
import { useSkeds } from "@/composables/useSkeds";
import { useSetupGuide, type SetupGuide } from "@/composables/useSetupGuide";
import { useStationActions } from "@/composables/useStationActions";
import { useStationCards } from "@/composables/useStationCards";
import { useStationAlerts } from "@/composables/useStationAlerts";
import { useStationKeys } from "@/composables/useStationKeys";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { useTitle } from "@/composables/useTitle";
import { pageVisible } from "@/composables/useVisible";
import { useWhatsNew } from "@/composables/useWhatsNew";
import { agingOf, type Aging } from "@/lib/aging";
import { headerPills } from "@/lib/pills";
import { enabledRadios, listensOnly, pageRadios, portsAsks } from "@/lib/radios";
import { rxSwitch } from "@/lib/rxswitch";
import { RX_ONLY_KEY } from "@/lib/settings";
import { inApp } from "@/lib/shell";
import { recommendedPath } from "@/lib/symbols";
import type { ConfigValues, RadioRow } from "@/protocol/protocol";

const NO_RADIOS: ReadonlyMap<string, RadioRow> = new Map();

function useShellRadios(daemon: ReturnType<typeof useDaemon>) {
  const all = computed(() => pageRadios(daemon.radios.value ?? NO_RADIOS, daemon.config.value));
  const enabled = computed(() => enabledRadios(all.value));
  return { all, enabled };
}

/**
 * The guide opens once, when the daemon says it has no call: not again when the settings are sent
 * again.
 */
function openGuideOnce(config: Readonly<Ref<ConfigValues | null>>, guide: SetupGuide): void {
  let shown = false;
  watch(
    () => config.value?.values["station/call"] === "",
    (empty) => {
      if (empty && !shown) {
        shown = true;
        guide.show();
      }
    },
    { immediate: true },
  );
}

function useDerived(daemon: ReturnType<typeof useDaemon>) {
  const { config, status, lastError, send } = daemon;
  const radios = useShellRadios(daemon);
  const settings = useSettings(config, lastError, send, daemon, {
    byId: (id: number) => radios.all.value.find((radio) => radio.id === id),
  });
  const prefs = useStationPrefs(daemon.stationPrefs, send);
  const keys = useStationKeys(daemon.stationKeys, status, send);
  const heard = useHeardIndex(daemon.stations, config);
  const now = useNow();
  const app = inApp();
  const listening = computed(() => listensOnly(daemon.radios.value));
  return {
    ...heard,
    settings,
    prefs,
    keys,
    now,
    dark: useDark(),
    aging: computed<Aging>(() => agingOf(config.value?.values)),
    // RX only as soon as it is asked for; transmitting again only once the daemon has it.
    receiveOnly: computed(
      () =>
        config.value?.values[RX_ONLY_KEY] === "false" || settings.expected(RX_ONLY_KEY) === "false" || listening.value,
    ),
    rxSwitch: computed(() =>
      config.value === null
        ? null
        : rxSwitch(settings.expected(RX_ONLY_KEY), listening.value, daemon.connection.value, radios.enabled.value[0]),
    ),
    // RX only goes before other waiting saves; transmitting again keeps its place.
    setTransmit: (on: boolean): void => settings.change({ [RX_ONLY_KEY]: String(on) }, !on),
    pills: computed(() =>
      headerPills(
        config.value?.values ?? {},
        daemon.gps.value,
        daemon.igate.value,
        daemon.status.value?.update ?? null,
        {
          connection: daemon.connection.value,
          now: now.value,
          inApp: app,
          radios: radios.all.value,
          told: daemon.radios.value !== null,
        },
        daemon.map.value,
      ),
    ),
    call: computed<string | null>(() => config.value?.values["station/call"] ?? status.value?.call ?? null),
    home: useHome(config, status),
    fallbackPath: computed(() => {
      const values = config.value?.values ?? {};
      return recommendedPath(values["station/symbol_table"] ?? "", values["station/symbol_code"] ?? "");
    }),
    connected: computed(() => radios.enabled.value.some((radio) => radio.connected)),
  };
}

/**
 * The tab models with something unseen, and the count of them all (header, folded panel handle,
 * browser tab title).
 */
function useTabs(daemon: ReturnType<typeof useDaemon>, panel: ReturnType<typeof usePanel>) {
  const { messages, send } = daemon;
  const talk = useMessagesView(messages, panel, send, daemon.messagesLoaded);
  const mail = useEmail(messages, panel, send, daemon.messagesLoaded);
  const board = useBulletins(daemon.bulletins, panel, daemon.bulletinsLoaded);
  const sked = useSkeds(
    daemon.skeds,
    panel,
    send,
    computed(() => daemon.connection.value === "open"),
  );
  const alerts = useBrowserAlerts(talk.writeTo);
  usePageAlerts(messages, daemon.messagesLoaded, alerts.announce);
  const unread = computed(() => talk.unread.value + mail.unread.value);
  useTitle(unread, alerts.tabTitle);
  /**
   * The header mail: the Messages tab, or the Email tab when the unseen messages are all the
   * gateway's.
   */
  function openUnread(): void {
    if (talk.unread.value > 0 || mail.unread.value === 0) talk.openMessages();
    else panel.show("email");
  }
  return { talk, mail, board, sked, alerts, unread, openUnread };
}

/**
 * The update windows: the steps panel, open on purpose and gone with the newer version, and the
 * notes (useWhatsNew).
 */
function useUpdateWindows(daemon: ReturnType<typeof useDaemon>) {
  const updateOpen = ref(false);
  const newer = computed(() => daemon.status.value?.update?.version ?? null);
  watch(newer, (version) => version === null && (updateOpen.value = false));
  const whatsNew = useWhatsNew(daemon.version);
  return { updateOpen, newer, whatsNew };
}

/**
 * The cards that open from the map's menu, in order from the map's right edge, with the width of
 * each (card.css).
 */
const OVERLAYS = ["stats", "packets", "monitor"] as const;
type Overlay = (typeof OVERLAYS)[number];
const CARD_PX: Record<Overlay, number> = { stats: 340, packets: 560, monitor: 560 };
const MARGIN_PX = 10;

/**
 * What opens over the map from its menu: the statistics card, the Packets card, the monitor and
 * the replay; `closeOverlays` closes them and says whether one was open. The cards stand side by
 * side where the map has room; where it has not, opening one closes those that leave it no room,
 * and remembered-open cards that do not fit beside the ones before them (OVERLAYS' order) stay
 * hidden until there is room. The monitor is shown only while a radio has a scope.
 */
function useMapOverlays(
  scopeAvailable: Readonly<Ref<boolean>>,
  phone: Readonly<Ref<boolean>>,
  mapWidth: Readonly<Ref<number>>,
) {
  // Each open from the map's menu, closed by its cross or Esc, and remembered by this browser.
  const open: Record<Overlay, WritableComputedRef<boolean>> = {
    stats: usePersistedFlag("stats", ["open", "closed"], false),
    packets: usePersistedFlag("packets", ["open", "closed"], false),
    monitor: usePersistedFlag("monitor", ["open", "closed"], false),
  };
  const available = (card: Overlay): boolean => card !== "monitor" || scopeAvailable.value;
  const fits = (cards: readonly Overlay[]): boolean =>
    cards.length <= 1 ||
    (!phone.value &&
      (mapWidth.value === 0 || cards.reduce((px, card) => px + CARD_PX[card] + MARGIN_PX, 0) <= mapWidth.value));
  const shown = computed(() =>
    OVERLAYS.reduce<Overlay[]>(
      (kept, card) => (open[card].value && available(card) && fits([...kept, card]) ? [...kept, card] : kept),
      [],
    ),
  );
  for (const card of OVERLAYS) {
    watch(open[card], (on) => {
      if (!on) return;
      const kept: Overlay[] = [card];
      for (const other of OVERLAYS) {
        if (other === card || !open[other].value || !available(other)) continue;
        if (fits([...kept, other])) kept.push(other);
        else open[other].value = false;
      }
    });
  }
  // The map replay: open from the map's menu, closed by its cross or Esc, not remembered.
  const replayOpen = ref(false);
  const closeReplay = (): boolean => {
    const was = replayOpen.value;
    replayOpen.value = false;
    return was;
  };
  const closeOverlays = (): boolean => {
    const cards = shown.value;
    for (const card of cards) open[card].value = false;
    return [cards.length > 0, closeReplay()].some(Boolean);
  };
  const isShown = (card: Overlay) => computed(() => shown.value.includes(card));
  return {
    statsOpen: open.stats,
    packetsOpen: open.packets,
    monitorOpen: open.monitor,
    statsShown: isShown("stats"),
    packetsShown: isShown("packets"),
    monitorShown: isShown("monitor"),
    replayOpen,
    closeOverlays,
  };
}

/**
 * What the radios hold now as one text: the ports list says who holds each device, so it is asked
 * again when this changes.
 */
const holdsOf = (rows: Iterable<RadioRow>): string =>
  [...rows]
    .map(
      (row) =>
        `${row.id}:${row.type}:${row.enabled}:${row.removed}:${row.holds.map((held) => `${held.resource}=${held.value}`).join(",")}`,
    )
    .sort()
    .join(";");

/**
 * The ports the system lists: asked each time the daemon is connected, and once the topic `radios`
 * is sent so that a radio with sound cards is asked for by id; asked again whenever what the radios
 * hold changes, because the list says who holds each device.
 */
function askPortsOnOpen(daemon: ReturnType<typeof useDaemon>): void {
  const { connection, radios, send } = daemon;
  let owed = false;
  let asked: string | null = null;
  const ask = (): void => {
    if (connection.value !== "open" || radios.value === null) return;
    const holds = holdsOf(radios.value.values());
    if (!owed && holds === asked) return;
    owed = false;
    asked = holds;
    for (const one of portsAsks(radios.value.values())) send(one);
  };
  watch(connection, (state) => {
    owed = state === "open";
    ask();
  });
  watch(radios, ask);
}

export function useAppShell() {
  const daemon = useDaemon();
  const { config, connection, lastError, send } = daemon;
  askPortsOnOpen(daemon);
  const derived = useDerived(daemon);
  const guide = useSetupGuide(config, lastError, send, daemon.radios, connection, daemon.saved);
  openGuideOnce(config, guide);
  const panel = usePanel();
  const tabs = useTabs(daemon, panel);

  const { updateOpen, newer, whatsNew } = useUpdateWindows(daemon);

  const objects = useOwnObjects(daemon.ownObjects, send, panel);
  const picks = useMapPicks(guide, objects);
  // The page size, what a phone shows (map or tab), and the station cards.
  const layout = useLayout(
    panel,
    computed(() => guide.open),
    picks.pickingTab,
  );
  // Esc ends a place the map waits for, then leaves the selected object and clears the form, before
  // the cards take the Esc that is left.
  const escBlocked = () => guide.open || updateOpen.value || whatsNew.open.value !== null;
  useFormEsc({
    cancelPick: () => {
      const waiting = picks.pickingTab.value;
      if (waiting) picks.cancel();
      return waiting;
    },
    closeForm: () => {
      const inSight = objects.dirty && panel.tab.value === "objects" && panel.onScreen.value;
      if (inSight) objects.cancel();
      return inSight;
    },
    blocked: escBlocked,
  });
  const scope = useScopeLooks(send, connection, pageVisible(), { radios: daemon.radios });
  const level = useRadioAsks("radio_level", send, connection, pageVisible(), () => null);
  const mapwrap = ref<HTMLElement | null>(null);
  const mapWidth = useElementWidth(mapwrap);
  const overlays = useMapOverlays(scope.available, layout.phone, mapWidth);
  const traffic = useLayerThings({
    ...daemon,
    visible: pageVisible(),
    replay: overlays.replayOpen,
    now: derived.now,
    store: daemon.layerTables,
  });
  const satellites = useSatellites({
    ...daemon,
    visible: pageVisible(),
    replay: overlays.replayOpen,
    store: daemon.satelliteStore,
  });
  const cards = useStationCards(derived.stations, send, layout, escBlocked, daemon.stationsLoaded, () =>
    [overlays.closeOverlays(), traffic.close(), satellites.close()].some(Boolean),
  );
  // The notices, what a Stations table row's menu sends or copies, and the station alerts that
  // fire.
  const { notice, say } = useNotice();
  const stationActions = useStationActions(send, say);
  useStationAlerts(daemon.stationAlert, tabs.alerts, say);
  const findRadio = useFindRadio(daemon.radioSearch, lastError, connection, send, derived.settings, config, say);

  provideDaemon({
    ...daemon,
    scope,
    level,
    traffic,
    satellites,
    weatherSeries: daemon.weatherSeriesByCall,
    ...derived,
    guide,
    panel,
    findRadio,
    alerts: tabs.alerts,
    say,
  });

  return {
    daemon,
    updateOpen,
    newer,
    whatsNew,
    objects,
    picks,
    layout,
    cards,
    ...overlays,
    mapwrap,
    guide,
    panel,
    notice,
    findRadio,
    stationActions,
    ...tabs,
    ...derived,
  };
}
