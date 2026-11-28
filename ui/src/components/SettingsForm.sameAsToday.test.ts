// Baseline: with the Packet radio alone, the Settings tab groups other than Radio, and the My station
// tab, draw the same ids and fields as with a single radio, and the header marks stay
// the same. Do not edit the expectations to make a change pass. What the radios' own settings
// changed is noted where it applies (radio 1's digipeater and path ids are `set-radio-1-digipeat`
// and `set-radio-1-path`).
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

/**
 * What each group other than Radio draws: its legends, the ids inside it (generated `v-N` ids and
 * the group body's own are left out) and the number of fields.
 */
function drawn(extra: Record<string, string>, scope: Scope, more: Given = {}): Record<string, Box> {
  localStorage.setItem("NeoAPRS.alert.mode", "both");
  const own = (radio: boolean) =>
    Object.fromEntries(Object.entries(extra).filter(([key]) => key.startsWith("radio/") === radio));
  const daemon = fakeDaemon({ config: configValues(own(false), own(true)), ...more });
  const wrapper = mount(SettingsForm, { props: { scope }, global: withDaemon(daemon) });
  const out: Record<string, Box> = {};
  for (const group of wrapper.findAll("form > fieldset")) {
    const title = group.find("legend").text();
    if (title === "Radio") continue;
    out[title] = {
      legends: group.findAll("legend").map((l) => l.text()),
      ids: group
        .findAll("[id]")
        .flatMap((e) =>
          /^(v-\d+|settings-group-.*)$/.test(e.attributes("id") ?? "") ? [] : [e.attributes("id") ?? ""],
        ),
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
  "Internet (APRS-IS)": only("Internet (APRS-IS)", ["set-igate-enabled", "set-igate-gate"]),
  Digipeater: only("Digipeater", ["set-radio-1-digipeat"]),
  "Web page": only("Web page", ["set-web-network"]),
  Notifications: NOTIFICATIONS,
  // the radius, and in a box for each layer its source: the receiver's address is there with My own
  // receiver, and its room in the Aircraft box with another; the room of AISStream's key is kept in
  // the Ships box
  Map: box(
    ["set-map-radius_km", "set-map-aircraft", "set-map-aircraft_host", "set-map-ships", "set-map-ships_key"],
    5,
    ["Map", "Aircraft", "Ships"],
  ),
  "Update check": only("Update check", ["set-update-now"]),
  Help: box(["set-help-send"], 1, ["Help"]),
  About: box(["set-help-logs"], 0, ["About"]),
};
const STATION = [
  "set-station-call",
  "set-station-call-ssid",
  "set-gps-source",
  "set-station-place",
  "set-station-symbol-change",
];

describe("the Settings tab and the My station tab with the Packet radio alone", () => {
  it("draw the groups other than Radio as they were before the Mercury radio", () => {
    expect(drawn({}, "settings")).toEqual(SETTINGS_TAB);
  });

  it("draw them so with the Digipeater, the iGate and the network on, and the radio's states told", () => {
    const busy = {
      "radio/1/digipeat": "true",
      "igate/enabled": "true",
      "web/network": "true",
      "web/key": "abc",
      "web/https": "true",
      "map/radius_km": "50",
    };
    expect(drawn(busy, "settings", { igate: igateState() })).toEqual({
      ...SETTINGS_TAB,
      "Web page": box(["set-web-network", "set-web-key", "set-web-https"], 3, ["Web page"]),
    });
  });

  it("draw the My station tab as before", () => {
    const fixed = {
      Station: box(STATION, 4, ["Station"]),
      Beacon: box(["set-beacon-interval_min", "set-station-comment", "set-beacon-power_w", "set-radio-1-path"], 4, [
        "Beacon",
      ]),
      Status: box(["set-status-source"], 1, ["Status"]),
    };
    expect(drawn({}, "beacon")).toEqual(fixed);
  });

  it("draw the My station tab of a moving station as before", () => {
    expect(drawn({ "gps/source": "serial", "beacon/power_w": "5", "status/source": "rigctld" }, "beacon")).toEqual({
      Station: box(
        [
          "set-station-call",
          "set-station-call-ssid",
          "set-gps-source",
          "set-gps-device",
          "set-gps-baud",
          "set-station-symbol-change",
        ],
        5,
        ["Station"],
      ),
      Beacon: box(["set-beacon-interval_min", "set-beacon-travel", "set-station-comment", "set-radio-1-path"], 4, [
        "Beacon",
      ]),
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

// The header with the Packet radio alone: the marks with their words, titles and colours.
describe("the header with the Packet radio alone", () => {
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

  it("is the Server mark and the radio's mark by its name, mint while connected, whether the Mercury radio's topic is there or not", () => {
    const today = [
      ["SPAN", "NeoAPRS", "The page is connected to NeoAPRS", "tag-ok pill-daemon"],
      ["BUTTON", "Packet", "Packet: connected. Settings → Radio", "tag-ok pill-radio"],
    ];
    expect(marks(open)).toEqual(today);
    expect(marks({ ...open, radios: pageRadiosOf(fmRow(), hfRow({ enabled: false, state: "stopped" })) })).toEqual(
      today,
    );
  });

  it("is the radio's mark on the warn plate with the state in words after its name: waiting, silent, not connected, searching", () => {
    const radio = (row: Parameters<typeof fmRow>[0] | null) =>
      marks({ ...open, radios: row === null ? [] : pageRadiosOf(fmRow(row)), told: row !== null })[1];
    expect(radio(null)).toEqual([
      "BUTTON",
      "Radio: waiting…",
      "No word from the radio yet. Settings → Radio",
      "tag-warn pill-radio",
    ]);
    // the title says the state in the page's words; "entering KISS" is no state of a radio's row
    expect(radio({ state: "waiting", problem: { code: "radio.not_connected", params: { name: "Packet" } } })).toEqual([
      "BUTTON",
      "Packet: not connected",
      "Not connected. Settings → Radio",
      "tag-warn pill-radio",
    ]);
    expect(radio({ state: "connecting", problem: { code: "radio.searching", params: {} } })?.[1]).toBe(
      "Packet: searching…",
    );
    expect(marks({ ...open, radios: pageRadiosOf(radioRow(1, "dummy")) })[1]).toEqual([
      "BUTTON",
      "Packet",
      "Dummy radio: made-up traffic, nothing goes on the air. Settings → Radio",
      "tag-dummy pill-radio",
    ]);
  });

  it("keeps the other marks of the station where they were, after the radio's mark, and none for RX only", () => {
    const rx = marks(open, { "station/transmit": "false" }).map((m) => m[1]);
    expect(rx).toEqual(["NeoAPRS", "Packet"]);
    const beaconOff = marks(open, { "beacon/interval_min": "0" }).map((m) => m[1]);
    expect(beaconOff).toEqual(["NeoAPRS", "Packet", "Beacon off"]);
  });
});
