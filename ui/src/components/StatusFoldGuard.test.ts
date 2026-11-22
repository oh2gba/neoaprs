// The rule for every status row of the page (StatusFold): the arrow, and a click that opens
// something, only when there is something behind it. A row that says "No beacon sent yet · next
// in 38 min" and opens nothing is a lie. This checks each component that makes a status row, with
// nothing behind it and with something; it fails for a new use of StatusFold that is not listed
// here, so that it gets its two cases.
import { mount } from "@vue/test-utils";
import { readdirSync, readFileSync } from "node:fs";
import { basename, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import BeaconStatus from "@/components/BeaconStatus.vue";
import DigipeaterStatus from "@/components/DigipeaterStatus.vue";
import IgateStatus from "@/components/IgateStatus.vue";
import ObjectsQru from "@/components/ObjectsQru.vue";
import RadioStatus from "@/components/RadioStatus.vue";
import StatusReportRow from "@/components/StatusReportRow.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, fmRow, igateState, lineStats, NOW, qruState, status } from "@/test/fixtures";

const SRC = resolve(__dirname, "..");
const later = new Date(NOW + 38 * 60_000).toISOString();

function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? vueFiles(resolve(dir, entry.name))
      : entry.name.endsWith(".vue")
        ? [resolve(dir, entry.name)]
        : [],
  );
}

/** Each component that draws a StatusFold: a row with nothing behind it (null if it always has
 * something) and a row with something. */
const ROWS: Record<string, { bare: (() => ReturnType<typeof mount>) | null; full: () => ReturnType<typeof mount> }> = {
  BeaconStatus: {
    bare: () =>
      mount(BeaconStatus, {
        props: { status: status({ beacon_interval_min: 60, beacon_next_due: later }), gps: null, values: {}, now: NOW },
      }),
    full: () =>
      mount(BeaconStatus, {
        props: {
          status: status({ beacon_interval_min: 60, beacon_next_due: later, beacon_last_sent: ago(240) }),
          gps: null,
          values: {},
          now: NOW,
        },
      }),
  },
  StatusReportRow: {
    bare: () =>
      mount(StatusReportRow, {
        props: { text: "", lastSent: null, minutes: "", rig: "unused", beaconOff: false, rxOnly: false, now: NOW },
      }),
    full: () =>
      mount(StatusReportRow, {
        props: { text: "", lastSent: null, minutes: "30", rig: "unused", beaconOff: false, rxOnly: false, now: NOW },
      }),
  },
  DigipeaterStatus: {
    bare: () => mount(DigipeaterStatus, { props: { tnc: fmRow(), startedAt: null, now: NOW, rxOnly: false } }),
    full: () => mount(DigipeaterStatus, { props: { tnc: fmRow(), startedAt: ago(3600), now: NOW, rxOnly: false } }),
  },
  IgateStatus: {
    bare: null,
    full: () =>
      mount(IgateStatus, {
        props: {
          igate: igateState(),
          values: { "igate/server": "rotate.aprs2.net:14580", "map/radius_km": "50" },
          stations: 3,
        },
      }),
  },
  ObjectsQru: {
    bare: null, // (it shows only once something was asked, and then the request is behind it)
    full: () => mount(ObjectsQru, { global: withDaemon(fakeDaemon({ qru: qruState() })) }),
  },
  RadioStatus: {
    bare: null,
    full: () => mount(RadioStatus, { props: { row: fmRow(), now: NOW } }),
  },
};

describe("every status row", () => {
  it("is listed here: a component that draws a StatusFold and is not in the guard fails until it is", () => {
    const users = vueFiles(SRC)
      .filter((file) => !file.endsWith("StatusFold.vue") && readFileSync(file, "utf8").includes("<StatusFold"))
      .map((file) => basename(file, ".vue"));
    expect(users.sort()).toEqual(Object.keys(ROWS).sort());
  });

  for (const [name, { bare, full }] of Object.entries(ROWS)) {
    it(`${name} has the arrow when something is behind it`, () => {
      const wrapper = full();
      expect(wrapper.find("details.statusfold > summary.statushead").exists()).toBe(true);
      expect(wrapper.find(".statusflat").exists()).toBe(false);
      expect(wrapper.find(".disclosure-body").text().trim()).not.toBe("");
    });

    it(`${name} is a plain row, with no arrow and nothing to click, when nothing is behind it`, () => {
      if (bare === null) return; // (a row that always has something: the Terminal, the server and the filter)
      const wrapper = bare();
      expect(wrapper.find("details").exists()).toBe(false);
      expect(wrapper.find("summary").exists()).toBe(false);
      expect(wrapper.find(".statusfold.statusflat .tncstatus").text()).not.toBe("");
    });
  }

  it("is a pair's row of the Digipeater group: a plain row with nothing behind it, the arrow once it counts since a time or sent something", () => {
    const pair = (sent: number) => ({
      first: { id: 1, name: "FM radio", stats: lineStats() },
      second: {
        id: 2,
        name: "Mercury radio",
        stats: lineStats({ passed: [{ heard_on: 1, sent, sent_at: sent > 0 ? ago(60) : null, held: 0, too_long: 0 }] }),
      },
    });
    const bare = mount(DigipeaterStatus, { props: { pair: pair(0), startedAt: null, now: NOW, rxOnly: false } });
    expect([bare.find("details").exists(), bare.find(".statusfold.statusflat .tncstatus").text()]).toEqual([
      false,
      "None repeated yet",
    ]);
    for (const [startedAt, sent] of [
      [ago(3600), 0],
      [null, 2],
    ] as const) {
      const full = mount(DigipeaterStatus, { props: { pair: pair(sent), startedAt, now: NOW, rxOnly: false } });
      expect(full.find("details.statusfold > summary.statushead").exists()).toBe(true);
      expect(full.find(".disclosure-body").text().trim()).not.toBe("");
    }
  });

  it("is the Beacon row of the report: no beacon sent yet and the next in 38 min, and nothing opens", () => {
    const wrapper = ROWS["BeaconStatus"]?.bare?.();
    expect(wrapper?.find(".tncstatus").text()).toBe("No beacon sent yet · next in 38 min (every 60 min)");
    expect(wrapper?.find("details").exists()).toBe(false);
  });
});
