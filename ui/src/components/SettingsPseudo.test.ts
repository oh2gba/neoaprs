// The settings area drawn in the pseudo-locale (src/i18n/pseudo.ts): every word of the Settings tab, the Beacon tab's settings, the first-run guide, the guides for pop-ups, the certificate and the update, and the small panels, with the
// parts that show only sometimes switched on (the access key, the secure connection, the search for the radio, a map on disk). A text that still equals an English message of the catalogue was written by hand, not taken from it.
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import BeaconPane from "@/components/BeaconPane.vue";
import BrowserAlerts from "@/components/BrowserAlerts.vue";
import ConfirmRow from "@/components/ConfirmRow.vue";
import HttpsGuide from "@/components/HttpsGuide.vue";
import KeyScreen from "@/components/KeyScreen.vue";
import MapFetchButton from "@/components/MapFetchButton.vue";
import MapFetchNotes from "@/components/MapFetchNotes.vue";
import PopupHelp from "@/components/PopupHelp.vue";
import RadioStatus from "@/components/RadioStatus.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import SetupCall from "@/components/SetupCall.vue";
import SetupGuide from "@/components/SetupGuide.vue";
import SetupMap from "@/components/SetupMap.vue";
import SetupPosition from "@/components/SetupPosition.vue";
import SetupRadio from "@/components/SetupRadio.vue";
import SetupSymbol from "@/components/SetupSymbol.vue";
import SymbolField from "@/components/SymbolField.vue";
import SymbolPicker from "@/components/SymbolPicker.vue";
import UndoToast from "@/components/UndoToast.vue";
import UpdateDialog from "@/components/UpdateDialog.vue";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { en } from "@/i18n/en";
import { texts, type Message } from "@/i18n/message";
import { setLocale } from "@/i18n";
import type { HttpsState, PortsMessage } from "@/protocol/protocol";
import { fakeDaemon, withDaemon, type FakeDaemon } from "@/test/context";
import { configValues, mapFile, mapState, status, tncState } from "@/test/fixtures";

/** The words that come from the daemon or the user, or are the same in every language: they are what the page shows besides the catalogue's words. */
const ATTRIBUTES = ["title", "aria-label", "placeholder", "label"];
const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** The English texts of the catalogue of the areas of this file, as what they look like on the page (a value is any text); one of fewer than three letters is not looked for. */
const ENGLISH = Object.entries(en as Record<string, Message>)
  .filter(([id]) => /^(settings|beacon|setup|help)\./.test(id))
  .flatMap(([, message]) => texts(message))
  .filter((text) => text.replace(/\{\w+\}/g, "").trim().length >= 3)
  .map(
    (text) =>
      new RegExp(
        `^${text
          .split(/(\{\{|\}\}|\{\w+\})/)
          .map((p) => (p === "{{" ? "\\{" : p === "}}" ? "\\}" : /^\{\w+\}$/.test(p) ? ".+" : escape(p)))
          .join("")}$`,
      ),
  );
/** Words of the page that are the same as a message and come from elsewhere: the names of the symbols, a call, a unit. */
const ELSEWHERE = [
  "House",
  "Car",
  "Antenna",
  "Digipeater",
  "Weather station",
  "Boat",
  "Bike",
  "Van",
  "Truck",
  "Motorcycle",
  "Walker",
  "Portable",
  "Close",
  "N",
];

function untranslated(root: Element): string[] {
  const found: string[] = [];
  const seen = (text: string): void => {
    const plain = text.trim().replace(/\s+/g, " ");
    if (plain !== "" && !ELSEWHERE.includes(plain) && ENGLISH.some((re) => re.test(plain))) found.push(plain);
  };
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) seen(node.textContent ?? "");
  for (const el of root.querySelectorAll("*")) for (const a of ATTRIBUTES) if (el.hasAttribute(a)) seen(el.getAttribute(a) ?? "");
  return found;
}

const https: HttpsState = { on: true, port: 7304, fingerprint: "AB:CD:EF", problem: "" };
const ports: PortsMessage = {
  type: "ports",
  search: true,
  find: true,
  ports: [{ device: "/dev/ttyUSB0", description: "FT232R", hwid: "n/a", vid: null, pid: null }],
};

function daemon(extra: Record<string, string> = {}, more: Parameters<typeof fakeDaemon>[0] = {}): FakeDaemon {
  const config = ref({
    ...configValues({ "web/network": "true", "web/key": "abc-def-ghi", "web/https": "true", ...extra }),
    https,
    urls: ["http://neoaprs.local:7303/"],
  });
  return fakeDaemon({
    config,
    ports,
    map: mapState({ detail: mapFile(), state: "downloading", step: "area", percent: 49, downloaded: 340_000_000 }),
    tnc: tncState({ state: "waiting", path: "", searching: ["/dev/ttyUSB0"], problem: "no radio found" }),
    install: { kind: "deb", appimage: "", service: true, arch: "amd64" },
    status: status({ beacon_last_sent: new Date(Date.now() - 60_000).toISOString(), station_status: "QRV", rig_state: "on" }),
    ...more,
  });
}

const mounted: VueWrapper[] = [];
function draw(component: Parameters<typeof mount>[0], context: FakeDaemon | undefined, props: Record<string, unknown> = {}): HTMLElement {
  setLocale("en-XA");
  const wrapper = mount(component, { props, global: context ? withDaemon(context) : {}, attachTo: document.body });
  mounted.push(wrapper);
  return wrapper.element as HTMLElement;
}

afterEach(() => {
  vi.unstubAllGlobals();
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.replaceChildren();
});

describe("the settings area in the pseudo-locale", () => {
  it("draws the Settings tab with every text from the catalogue", async () => {
    const context = daemon();
    const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(context), attachTo: document.body });
    mounted.push(wrapper);
    setLocale("en-XA");
    await flushPromises();
    expect(wrapper.findAll("legend").map((l) => l.text())).toHaveLength(11); // (the nine groups and the two boxes of Notifications)
    expect(wrapper.findAll("legend").every((l) => l.text().startsWith("[!! "))).toBe(true);
    expect(wrapper.find("#set-web-key").exists()).toBe(true);
    expect(wrapper.find(".radiostatus").exists()).toBe(true);
    expect(untranslated(document.body)).toEqual([]);
    // the question under a switch, the Undo toast and the panel of the pop-ups open
    await wrapper.find("#alert-mode").setValue(true);
    expect(untranslated(document.body)).toEqual([]);
    await wrapper.find("#alert-enable-popups").trigger("click");
    expect(untranslated(document.body)).toEqual([]);
  });

  it("draws the Beacon tab with its folds and its status", async () => {
    const context = daemon({ "beacon/power_w": "5", "status/source": "rig", "beacon/interval_min": "30" });
    setLocale("en-XA");
    const wrapper = mount(BeaconPane, { global: withDaemon(context), attachTo: document.body });
    mounted.push(wrapper);
    await flushPromises();
    await flushPromises();
    expect(wrapper.text()).toMatch(/\[!! /);
    expect(untranslated(document.body)).toEqual([]);
  });

  it("draws the first-run guide, step by step", async () => {
    const context = daemon({ "station/call": "", "station/lat": "", "station/lon": "" });
    context.guide.show();
    expect(untranslated(draw(SetupGuide, context))).toEqual([]);
    for (const step of [SetupCall, SetupPosition, SetupSymbol, SetupRadio, SetupMap]) expect(untranslated(draw(step, context)), step.__name).toEqual([]);
    context.guide.edit("profile", "kiss-tcp");
    expect(untranslated(draw(SetupRadio, context))).toEqual([]);
    context.guide.edit("lat", "x");
    await flushPromises();
    expect(untranslated(draw(SetupPosition, context))).toEqual([]);
  });

  it("draws the guides for pop-ups, the certificate and the update", () => {
    const context = daemon();
    expect(untranslated(draw(PopupHelp, context, { https }))).toEqual([]);
    expect(untranslated(draw(PopupHelp, context, { https: null }))).toEqual([]);
    expect(untranslated(draw(HttpsGuide, context, { https }))).toEqual([]);
    expect(untranslated(draw(UpdateDialog, context, { version: "0.7.0" }))).toEqual([]);
    const job = { supported: true, state: "error", version: "0.7.0", percent: null, downloaded: 0, total: null, problem: "checksum", detail: "" } as const;
    context.selfUpdate.value = job;
    expect(untranslated(draw(UpdateDialog, context, { version: "0.7.0" }))).toEqual([]);
    context.selfUpdate.value = { ...job, state: "downloading", percent: 5, problem: "" };
    expect(untranslated(draw(UpdateDialog, context, { version: "0.7.0" }))).toEqual([]);
  });

  it("would notice a text written by hand", () => {
    const page = draw(ConfirmRow, undefined, { message: "x" });
    page.insertAdjacentHTML("beforeend", "<button>Reconnect</button><p title='Test sound'>x</p>");
    expect(untranslated(page)).toEqual(["Reconnect", "Test sound"]);
  });

  it("draws the steps of each browser", () => {
    const chrome = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";
    const agents = [
      "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
      chrome,
      `${chrome} Edg/140.0.0.0`,
      "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    ];
    for (const userAgent of agents) {
      vi.stubGlobal("navigator", { userAgent, maxTouchPoints: 0 });
      expect(untranslated(draw(PopupHelp, undefined, { https: null })), userAgent).toEqual([]);
      expect(untranslated(draw(HttpsGuide, undefined, { https })), userAgent).toEqual([]);
    }
  });

  it("draws the small panels", () => {
    const context = daemon();
    const guide = useSetupGuide(ref(configValues()), ref(null), ref(null), () => true);
    expect(untranslated(draw(KeyScreen, undefined))).toEqual([]);
    expect(untranslated(draw(ConfirmRow, undefined, { message: "x" }))).toEqual([]);
    expect(untranslated(draw(UndoToast, undefined, { undo: { label: "Position", values: {}, n: 1 } }))).toEqual([]);
    expect(untranslated(draw(SymbolPicker, undefined, { table: "/", code: "-" }))).toEqual([]);
    expect(untranslated(draw(SymbolField, undefined, { id: "s", symbol: "S#" }))).toEqual([]);
    expect(untranslated(draw(RadioStatus, undefined, { tnc: context.tnc.value, now: Date.now(), digipeater: true }))).toEqual([]);
    expect(untranslated(draw(MapFetchButton, undefined, { map: mapState({ detail: mapFile() }), stale: false, send: () => true }))).toEqual([]);
    expect(untranslated(draw(MapFetchNotes, undefined, { map: mapState({ detail: mapFile() }) }))).toEqual([]);
    expect(untranslated(draw(BrowserAlerts, context, { alerts: context.alerts, https }))).toEqual([]);
    expect(guide.open).toBeDefined();
  });
});
