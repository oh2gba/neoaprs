// The page put together (App.vue is its layout): the daemon, the clock, the settings that apply as they are changed, the first-run guide, the panel, the tabs' models, the station cards, the statistics card, the replay of the map, the aircraft and ships of the map's layers (composables/useLayerThings.ts: Esc closes a thing's card with the station cards) and the places picked on the map, with what the shell itself decides:
// the ports are asked for each time the daemon is connected, the guide opens once by itself when the daemon has no call, the steps of an update are open on purpose and go with the newer version, the notes of the version that runs open from Settings and from the
// line shown once after an update (useWhatsNew), and the mail of the header opens the tab that has the messages not seen. What the panes share is provided to them (`useDaemonContext`); what only the layout needs is returned.
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
import { inApp } from "@/lib/shell";
import { recommendedPath } from "@/lib/symbols";
import type { ConfigValues, RadioRow } from "@/protocol/protocol";

const NO_RADIOS: ReadonlyMap<string, RadioRow> = new Map();

/** The radios as the shell reads them (the panes read them through composables/useRadios.ts, which the shell itself cannot ask: it is the one that provides the page's context). */
function useShellRadios(daemon: ReturnType<typeof useDaemon>) {
  const all = computed(() => pageRadios(daemon.radios.value ?? NO_RADIOS, daemon.config.value));
  const enabled = computed(() => enabledRadios(all.value));
  return { all, enabled };
}

/** The guide opens once, when the daemon says it has no call (the page's first word of a fresh install): not again when the settings are told again, nor when the call is set. */
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

/** What the panes read of the daemon's state besides the topics themselves: who and where we are, the stations heard, how they age, the settings and the stations' own choices. */
function useDerived(daemon: ReturnType<typeof useDaemon>) {
  const { config, status, lastError, send } = daemon;
  const radios = useShellRadios(daemon);
  const settings = useSettings(config, lastError, send, { byId: (id: number) => radios.all.value.find((radio) => radio.id === id) }); // (a refusal of Save names its radio as the page does)
  const prefs = useStationPrefs(daemon.stationPrefs, send);
  const keys = useStationKeys(daemon.stationKeys, status, send);
  const heard = useHeardIndex(daemon.stations, config);
  const now = useNow();
  const app = inApp();
  return {
    ...heard,
    settings,
    prefs,
    keys,
    now,
    dark: useDark(),
    aging: computed<Aging>(() => agingOf(config.value?.values)),
    receiveOnly: computed(() => config.value?.values["station/transmit"] === "false" || listensOnly(daemon.radios.value)),
    pills: computed(() =>
      headerPills(
        config.value?.values ?? {},
        daemon.gps.value,
        daemon.igate.value,
        daemon.status.value?.update ?? null,
        { connection: daemon.connection.value, now: now.value, inApp: app, radios: radios.all.value, told: daemon.radios.value !== null },
        daemon.map.value,
        listensOnly(daemon.radios.value),
      ),
    ),
    call: computed<string | null>(() => config.value?.values["station/call"] ?? status.value?.call ?? null),
    home: useHome(config, status),
    fallbackPath: computed(() => {
      const values = config.value?.values ?? {};
      return recommendedPath(values["station/symbol_table"] ?? "", values["station/symbol_code"] ?? "");
    }),
    connected: computed(() => radios.enabled.value.some((radio) => radio.connected)), // (any radio that is on)
  };
}

/** The models of the tabs that have something not seen (messages, email, bulletins, skeds), and the count of them all: the one of the header, of the folded panel's handle and of the browser tab's title. */
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
  /** The mail of the header: the Messages tab, or the Email tab when the messages not seen are all the gateway's. */
  function openUnread(): void {
    if (talk.unread.value > 0 || mail.unread.value === 0) talk.openMessages();
    else panel.show("email");
  }
  return { talk, mail, board, sked, alerts, unread, openUnread };
}

/** The windows of an update: the panel with the steps of one, open on purpose and gone when the newer version is, and the notes of the version that runs (useWhatsNew). */
function useUpdateWindows(daemon: ReturnType<typeof useDaemon>) {
  const updateOpen = ref(false);
  const newer = computed(() => daemon.status.value?.update?.version ?? null);
  watch(newer, (version) => version === null && (updateOpen.value = false));
  const whatsNew = useWhatsNew(daemon.version);
  return { updateOpen, newer, whatsNew };
}

/** The cards that open over the map from its menu, in the order they stand from the map's right edge, and the width of each (card.css); each takes its width and the margin at its right. */
const OVERLAYS = ["stats", "packets", "monitor"] as const;
type Overlay = (typeof OVERLAYS)[number];
const CARD_PX: Record<Overlay, number> = { stats: 340, packets: 560, monitor: 560 };
const MARGIN_PX = 10;

/** What opens over the map from its menu: the statistics card, the Packets card, the monitor and the replay; closeOverlays closes them (an Esc the station cards pass on) and says whether one was open. The cards
 * stand side by side where the map has room for them; where it has not (a phone, a narrow map) opening one closes those that leave it no room, and of those remembered open the ones that do not fit beside the
 * ones before them (in OVERLAYS' order) are not shown until there is room or those are closed. The monitor is shown only while a radio has a scope. */
function useMapOverlays(scopeAvailable: Readonly<Ref<boolean>>, phone: Readonly<Ref<boolean>>, mapWidth: Readonly<Ref<number>>) {
  // each open from the map's menu, closed by its cross or Esc, and remembered by this browser
  const open: Record<Overlay, WritableComputedRef<boolean>> = {
    stats: usePersistedFlag("stats", ["open", "closed"], false), // components/StatsCard.vue
    packets: usePersistedFlag("packets", ["open", "closed"], false), // components/PacketsCard.vue
    monitor: usePersistedFlag("monitor", ["open", "closed"], false), // components/MonitorCard.vue, a radio's scope larger
  };
  const available = (card: Overlay): boolean => card !== "monitor" || scopeAvailable.value;
  /** Whether the cards fit side by side: one always does; a width not yet measured is room. */
  const fits = (cards: readonly Overlay[]): boolean =>
    cards.length <= 1 || (!phone.value && (mapWidth.value === 0 || cards.reduce((px, card) => px + CARD_PX[card] + MARGIN_PX, 0) <= mapWidth.value));
  const shown = computed(() =>
    OVERLAYS.reduce<Overlay[]>((kept, card) => (open[card].value && available(card) && fits([...kept, card]) ? [...kept, card] : kept), []),
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
  // the replay of the map (components/StationMap.vue runs it, composables/useMapReplay.ts): open from the map's menu, closed by its cross or Esc, the statistics card's way; not remembered, it is a look back for now
  const replayOpen = ref(false);
  const closeReplay = (): boolean => {
    const was = replayOpen.value;
    replayOpen.value = false;
    return was;
  };
  const closeOverlays = (): boolean => {
    const cards = shown.value; // (what is shown now: a card that is hidden stays remembered)
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

/** What the radios hold now, and which of them there are, as one text: the list of ports and sound cards says who holds each, so it is asked again when this changes. */
const holdsOf = (rows: Iterable<RadioRow>): string =>
  [...rows]
    .map((row) => `${row.id}:${row.type}:${row.enabled}:${row.removed}:${row.holds.map((held) => `${held.resource}=${held.value}`).join(",")}`)
    .sort()
    .join(";");

/** The ports the system lists, for the Settings tab and the setup guide: asked each time the daemon is connected (not before: a command then is refused with a toast), and only once the topic `radios` is told,
 * so that a radio with sound cards is asked for by its id (the connection opens with the hello, before the radios come; on a reconnect the radios kept are told already). And asked again whenever what the radios
 * hold changes (a radio let go of its sound card or its port: its type changed, it was switched off or removed): the list says who holds each device, and a card shown as held by a radio that let it go
 * could not be chosen for another. */
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
  const guide = useSetupGuide(config, lastError, send, daemon.radios);
  openGuideOnce(config, guide);
  const panel = usePanel();
  const tabs = useTabs(daemon, panel);

  const { updateOpen, newer, whatsNew } = useUpdateWindows(daemon);

  const objects = useOwnObjects(daemon.ownObjects, send, panel);
  const picks = useMapPicks(guide, objects);
  // the size of the page, what a phone shows (the map or the tab), and the station cards: one, or several with Ctrl+click on a desktop and a tablet
  const layout = useLayout(
    panel,
    computed(() => guide.open),
    picks.pickingTab,
  );
  // Esc ends a place the map waits for and then leaves the object selected in the Objects tab and clears its form (before the cards, which take the Esc that is left)
  const escBlocked = () => guide.open || updateOpen.value || whatsNew.open.value !== null;
  useFormEsc({
    cancelPick: () => {
      const waiting = picks.pickingTab.value;
      if (waiting) picks.cancel();
      return waiting;
    },
    closeForm: () => {
      const inSight = objects.dirty && panel.tab.value === "objects" && !panel.collapsed.value && (!layout.phone.value || layout.showing.value === "panel");
      if (inSight) objects.cancel();
      return inSight;
    },
    blocked: escBlocked,
  });
  const scope = useScopeLooks(send, connection, pageVisible(), { radios: daemon.radios });
  const level = useRadioAsks("radio_level", send, connection, pageVisible(), () => null);
  const mapwrap = ref<HTMLElement | null>(null); // (the map's box, bound by App.vue)
  const mapWidth = useElementWidth(mapwrap);
  const overlays = useMapOverlays(scope.available, layout.phone, mapWidth); // (what opens over the map from its menu: the cards, the replay)
  const traffic = useLayerThings({ ...daemon, visible: pageVisible(), replay: overlays.replayOpen, now: derived.now, store: daemon.layerTables }); // (the map's aircraft and ships)
  const cards = useStationCards(derived.stations, send, layout, escBlocked, daemon.stationsLoaded, () =>
    [overlays.closeOverlays(), traffic.close()].some(Boolean),
  );
  // the notices (a toast that is no error), what the menu of a row of the Stations table sends or copies, and the alerts set on stations that fire
  const { notice, say } = useNotice();
  const stationActions = useStationActions(send, say);
  useStationAlerts(daemon.stationAlert, tabs.alerts, say); // (an alert set on a station that fired: as a message alerts, and in the toast)
  const findRadio = useFindRadio(daemon.radioSearch, lastError, connection, send, derived.settings, config, say);

  provideDaemon({
    ...daemon,
    scope,
    level,
    traffic,
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
