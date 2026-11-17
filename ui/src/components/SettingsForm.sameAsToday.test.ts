// The two radios change the Radio group and nothing else (and the header's marks stay the same) for a station that has the FM radio alone: with radio 1 alone the groups of the Settings tab other than Radio, and the My station tab, draw the ids and the fields that the page drew before the HF radio
// existed. The expectations below were taken from that page (the commit before the two radios: 43025c0) and are not to be edited to make a change pass; what the radios' own settings changed is said where it is (the ids of radio 1's digipeater
// and path are its own, `set-radio-1-digipeat` and `set-radio-1-path`; the header says the state of the radio's row in the page's words).
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import AppHeader from "@/components/AppHeader.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { headerPills, type Link } from "@/lib/pills";
import type { Scope } from "@/lib/settings";
import { fakeDaemon, withDaemon, type Given } from "@/test/context";
import { pageRadios } from "@/lib/radios";
import type { RadioRow } from "@/protocol/protocol";
import { NOW, configValues, fmRow, hfRow, igateState, radioRow, radiosTopic } from "@/test/fixtures";

const pageRadiosOf = (...rows: RadioRow[]) => pageRadios(radiosTopic(...rows), null);

afterEach(() => localStorage.clear());

interface Box {
  legends: string[];
  ids: string[];
  fields: number;
}

/** What each group other than Radio draws: its legends, the ids inside it (the generated ones, `v-N`, and the group body's own, left out) and how many fields. */
function drawn(extra: Record<string, string>, scope: Scope, more: Given = {}): Record<string, Box> {
  localStorage.setItem("NeoAPRS.alert.mode", "both");
  const own = (radio: boolean) => Object.fromEntries(Object.entries(extra).filter(([key]) => key.startsWith("radio/") === radio));
  const daemon = fakeDaemon({ config: configValues(own(false), own(true)), ...more });
  const wrapper = mount(SettingsForm, { props: { scope }, global: withDaemon(daemon) });
  const out: Record<string, Box> = {};
  for (const group of wrapper.findAll("form > fieldset")) {
    const title = group.find("legend").text();
    if (title === "Radio") continue;
    out[title] = {
      legends: group.findAll("legend").map((l) => l.text()),
      ids: group.findAll("[id]").flatMap((e) => (/^(v-\d+|settings-group-.*)$/.test(e.attributes("id") ?? "") ? [] : [e.attributes("id") ?? ""])),
      fields: group.findAll(".field").length,
    };
  }
  return out;
}

const box = (ids: string[], fields = ids.length, legends: string[] = []): Box => ({ legends, ids, fields });
const NOTIFICATIONS = box(
  [
    "set-messages-alert",
    "set-messages-alert_command",
    "alert-mode",
    "alert-sound",
    "alert-test-sound",
    "alert-popup",
    "alert-test-popup",
    "alert-enable-popups",
  ],
  5,
  ["Notifications", "On the NeoAPRS computer i", "In this browser"],
);
const only = (title: string, ids: string[]): Box => box(ids, ids.length, [title]);
const SETTINGS_TAB = {
  "Internet stations": only("Internet stations", ["set-igate-enabled"]),
  "Ships (AIS)": box(["set-ais-enabled", "set-ais-types-label", "set-ais-types", "set-ais-hide_still", "set-ais-radius_km", "set-ais-track_min"], 5, [
    "Ships (AIS)",
  ]),
  "Aircraft (ADS-B)": only("Aircraft (ADS-B)", ["set-adsb-enabled", "set-adsb-radius_km", "set-adsb-track_min"]),
  Digipeater: only("Digipeater", ["set-radio-1-digipeat"]),
  "Web page": only("Web page", ["set-web-network"]),
  Notifications: NOTIFICATIONS,
  Map: only("Map", ["set-map-radius_km"]),
  "Update check": only("Update check", ["set-update-now"]),
  Help: box(["set-help-send"], 1, ["Help"]),
  About: box(["set-help-logs"], 0, ["About"]),
};
const STATION = ["set-station-call", "set-station-call-ssid", "set-gps-source", "set-station-place", "set-station-symbol-change"];

describe("the Settings tab and the My station tab with the FM radio alone", () => {
  it("draw the groups other than Radio as they were before the Mercury radio", () => {
    expect(drawn({}, "settings")).toEqual(SETTINGS_TAB);
  });

  it("draw them so with the Digipeater, the iGate and the network on, and the radio's states told", () => {
    const busy = { "radio/1/digipeat": "true", "igate/enabled": "true", "web/network": "true", "web/key": "abc", "web/https": "true", "map/radius_km": "50" };
    expect(drawn(busy, "settings", { igate: igateState() })).toEqual({
      ...SETTINGS_TAB,
      "Web page": box(["set-web-network", "set-web-key", "set-web-https"], 3, ["Web page"]),
    });
  });

  it("draw the My station tab as before", () => {
    const fixed = {
      Station: box(STATION, 4, ["Station"]),
      Beacon: box(["set-beacon-interval_min", "set-station-comment", "set-beacon-power_w", "set-radio-1-path"], 4, ["Beacon"]),
      Status: box(["set-status-source"], 1, ["Status"]),
    };
    expect(drawn({}, "beacon")).toEqual(fixed);
  });

  it("draw the My station tab of a moving station as before", () => {
    expect(drawn({ "gps/source": "serial", "beacon/power_w": "5", "status/source": "rigctld" }, "beacon")).toEqual({
      Station: box(["set-station-call", "set-station-call-ssid", "set-gps-source", "set-gps-device", "set-gps-baud", "set-station-symbol-change"], 5, [
        "Station",
      ]),
      Beacon: box(["set-beacon-interval_min", "set-beacon-travel", "set-station-comment", "set-radio-1-path"], 4, ["Beacon"]),
      Status: box(["set-status-source"], 1, ["Status"]),
    });
  });

  it("draw the My station tab of a fixed station with a power as before: the antenna and the path", () => {
    expect(drawn({ "beacon/power_w": "5", "beacon/interval_min": "0" }, "beacon")).toEqual({
      Station: box(STATION, 4, ["Station"]),
      Beacon: box(
        [
          "set-beacon-interval_min",
          "set-station-comment",
          "set-beacon-power_w",
          "set-beacon-antenna_height_m",
          "set-beacon-antenna_gain_db",
          "set-beacon-antenna_direction",
          "set-radio-1-path",
        ],
        7,
        ["Beacon"],
      ),
      Status: box(["set-status-source"], 1, ["Status"]),
    });
  });
});

// The header with the FM radio alone: the marks of the page before the HF radio existed, with their words, titles and colours (taken from that page, like the lists above).
describe("the header with the FM radio alone", () => {
  const marks = (link: Link, values: Record<string, string> = {}) => {
    const wrapper = mount(AppHeader, {
      props: { call: "OH2GBA", unread: 0, pills: headerPills(values, null, null, null, link) },
    });
    return wrapper.findAll(".headpills .tag").map((m) => [
      m.element.tagName,
      m.text(),
      m.attributes("title"),
      m
        .classes()
        .filter((c) => c.startsWith("tag-") || c.startsWith("pill-"))
        .join(" "),
    ]);
  };
  const open: Link = { connection: "open", radios: pageRadiosOf(fmRow()), now: NOW, inApp: false, told: true };

  it("is the Server mark and the one Radio mark, mint while connected, whether the Mercury radio's topic is there or not", () => {
    const today = [
      ["SPAN", "NeoAPRS", "The page is connected to NeoAPRS", "tag-ok pill-daemon"],
      ["BUTTON", "Radio", "Radio connected. Settings → Radio", "tag-ok pill-radio"],
    ];
    expect(marks(open)).toEqual(today);
    expect(marks({ ...open, radios: pageRadiosOf(fmRow(), hfRow({ enabled: false, state: "stopped" })) })).toEqual(today);
  });

  it("is the Radio mark on the warn plate with the state in words, as it was: waiting, silent, not connected, searching", () => {
    const radio = (row: Parameters<typeof fmRow>[0] | null) => marks({ ...open, radios: row === null ? [] : pageRadiosOf(fmRow(row)), told: row !== null })[1];
    expect(radio(null)).toEqual(["BUTTON", "Radio: waiting…", "No word from the radio yet. Settings → Radio", "tag-warn pill-radio"]);
    // (the daemon's English reason of before is the log's: the title says the state in the page's words; "entering KISS" is no state of a radio's row)
    expect(radio({ state: "waiting", problem: { code: "radio.not_connected", params: { name: "FM" } } })).toEqual([
      "BUTTON",
      "Radio: not connected",
      "Not connected. Settings → Radio",
      "tag-warn pill-radio",
    ]);
    expect(radio({ state: "connecting", problem: { code: "radio.searching", params: {} } })?.[1]).toBe("Radio: searching…");
    expect(marks({ ...open, radios: pageRadiosOf(radioRow(1, "dummy")) })[1]).toEqual([
      "BUTTON",
      "Radio",
      "Dummy radio: made-up traffic, nothing goes on the air. Settings → Radio",
      "tag-dummy pill-radio",
    ]);
  });

  it("keeps the other marks of the station where they were, after the Radio mark", () => {
    const rx = marks(open, { "station/transmit": "false" }).map((m) => m[1]);
    expect(rx).toEqual(["NeoAPRS", "Radio", "RX only"]);
    const beaconOff = marks(open, { "beacon/interval_min": "0" }).map((m) => m[1]);
    expect(beaconOff).toEqual(["NeoAPRS", "Radio", "Beacon off"]);
  });
});
