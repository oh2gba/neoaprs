// The page put together (App.vue is its layout): the daemon, the clock, the settings that apply as they are changed, the first-run guide, the panel, the tabs' models, the station cards and the places picked on the map, with what the shell itself decides:
// the ports are asked for each time the daemon is connected, the guide opens once by itself when the daemon has no call, the steps of an update are open on purpose and go with the newer version, and the mail of the header opens the tab that has the messages
// not seen. What the panes share is provided to them (`useDaemonContext`); what only the layout needs is returned.
import { computed, ref, watch, type Ref } from "vue";
import { provideDaemon } from "@/composables/useDaemonContext";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { useBulletins } from "@/composables/useBulletins";
import { useDaemon } from "@/composables/useDaemon";
import { useDark } from "@/composables/useDark";
import { useEmail } from "@/composables/useEmail";
import { useFindRadio } from "@/composables/useFindRadio";
import { useFormEsc } from "@/composables/useFormEsc";
import { useHeardIndex } from "@/composables/useHeardIndex";
import { useHome } from "@/composables/useHome";
import { useLayout } from "@/composables/useLayout";
import { useMapPicks } from "@/composables/useMapPicks";
import { useMessagesView } from "@/composables/useMessagesView";
import { useNotice } from "@/composables/useNotice";
import { useNow } from "@/composables/useNow";
import { useOwnObjects } from "@/composables/useOwnObjects";
import { usePageAlerts } from "@/composables/usePageAlerts";
import { usePanel } from "@/composables/usePanel";
import { useSettings } from "@/composables/useSettings";
import { useSetupGuide, type SetupGuide } from "@/composables/useSetupGuide";
import { useStationActions } from "@/composables/useStationActions";
import { useStationCards } from "@/composables/useStationCards";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { useTitle } from "@/composables/useTitle";
import { agingOf, type Aging } from "@/lib/aging";
import { pathCalls } from "@/lib/calls";
import { headerPills } from "@/lib/pills";
import { recommendedPath } from "@/lib/symbols";
import type { ConfigValues } from "@/protocol/protocol";

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
  const { config, status, tnc, lastError, send } = daemon;
  const settings = useSettings(config, lastError, send);
  const prefs = useStationPrefs(daemon.stationPrefs, send);
  const heard = useHeardIndex(daemon.stations, config);
  return {
    ...heard,
    settings,
    prefs,
    now: useNow(),
    dark: useDark(),
    aging: computed<Aging>(() => agingOf(config.value?.values)),
    receiveOnly: computed(() => config.value?.values["station/transmit"] === "false"),
    pills: computed(() => headerPills(config.value?.values ?? {}, daemon.gps.value, daemon.igate.value)),
    call: computed<string | null>(() => config.value?.values["station/call"] ?? status.value?.call ?? null),
    home: useHome(config, status),
    fallbackPath: computed(() => {
      const values = config.value?.values ?? {};
      const text = values["beacon/path"] ?? "";
      return (pathCalls(text, recommendedPath(values["station/symbol_table"] ?? "", values["station/symbol_code"] ?? "")) ?? [text]).join(",");
    }),
    connected: computed(() => tnc.value?.state === "connected"),
  };
}

/** The models of the tabs that have messages not seen, and the count of them all: the one of the header, of the folded panel's handle and of the browser tab's title. */
function useTabs(daemon: ReturnType<typeof useDaemon>, panel: ReturnType<typeof usePanel>) {
  const { messages, send } = daemon;
  const talk = useMessagesView(messages, panel, send);
  const mail = useEmail(messages, panel, send);
  const board = useBulletins(daemon.bulletins, panel);
  const alerts = useBrowserAlerts(talk.writeTo);
  usePageAlerts(messages, daemon.messagesLoaded, alerts.announce);
  const unread = computed(() => talk.unread.value + mail.unread.value);
  useTitle(unread, alerts.tabTitle);
  /** The mail of the header: the Messages tab, or the Email tab when the messages not seen are all the gateway's. */
  function openUnread(): void {
    if (talk.unread.value > 0 || mail.unread.value === 0) talk.openMessages();
    else panel.show("email");
  }
  return { talk, mail, board, alerts, unread, openUnread };
}

export function useAppShell() {
  const daemon = useDaemon();
  const { config, status, connection, lastError, send } = daemon;
  // the ports the system lists, for the Settings tab and the setup guide: asked each time the daemon is connected (not before: a command then is refused with a toast)
  watch(connection, (state) => {
    if (state === "open") send({ cmd: "list_ports" });
  });
  const derived = useDerived(daemon);
  const guide = useSetupGuide(config, lastError, daemon.ports, send, daemon.map);
  openGuideOnce(config, guide);
  const panel = usePanel();
  const tabs = useTabs(daemon, panel);

  // the panel with the steps of an update is open on purpose, and goes when the newer version does
  const updateOpen = ref(false);
  const newer = computed(() => status.value?.update?.version ?? null);
  watch(newer, (version) => version === null && (updateOpen.value = false));

  const objects = useOwnObjects(daemon.ownObjects, send, panel);
  const picks = useMapPicks(guide, objects);
  // the size of the page, what a phone shows (the map or the tab), and the station cards: one, or several with Ctrl+click on a desktop and a tablet
  const layout = useLayout(
    panel,
    computed(() => guide.open),
    picks.pickingTab,
  );
  // Esc ends a place the map waits for and then leaves the object selected in the Objects tab and clears its form (before the cards, which take the Esc that is left)
  const escBlocked = () => guide.open || updateOpen.value;
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
  const cards = useStationCards(derived.stations, send, layout, escBlocked, daemon.stationsLoaded);
  // the notices (a toast that is no error) and what the menu of a row of the Stations table sends or copies
  const { notice, say } = useNotice();
  const stationActions = useStationActions(send, say);
  const findRadio = useFindRadio(daemon.radioSearch, lastError, connection, send, derived.settings, config, say, guide);

  provideDaemon({
    ...daemon,
    weatherSeries: daemon.weatherSeriesByCall,
    ...derived,
    guide,
    panel,
    findRadio,
    alerts: tabs.alerts,
    say,
  });

  return { daemon, updateOpen, newer, objects, picks, layout, cards, guide, panel, notice, findRadio, stationActions, ...tabs, ...derived };
}
