import { describe, expect, it } from "vitest";
import { clockText } from "@/lib/format";
import { localLine, searchedPorts, tncCounts, tncStatus } from "@/lib/tncstatus";
import { NOW, ago, tncState } from "@/test/fixtures";

const searching = () =>
  tncState({
    state: "waiting",
    path: "",
    describe: "listening on /dev/ttyUSB0, /dev/serial/by-id/usb-X-if00 for the radio",
    stats: { ...tncState().stats, packets: 0 },
  });

describe("tncStatus", () => {
  it("says what it is connected to and when the last packet came", () => {
    const tnc = tncState({ path: "/dev/ttyUSB0", stats: { ...tncState().stats, packets: 412, last_packet: ago(120) } });
    expect(tncStatus(tnc, NOW)).toBe("Last packet 2 min ago");
  });

  it("adds how many packets the digipeater repeated, only while it is on and only when there were some", () => {
    const tnc = tncState({ stats: { ...tncState().stats, digipeated: 3 } });
    expect(tncStatus(tnc, NOW, true)).toBe("Last packet 30 s ago, digipeated 3");
    expect(tncStatus(tnc, NOW, false)).not.toContain("digipeated");
    expect(tncStatus(tncState(), NOW, true)).not.toContain("digipeated");
  });

  it("says so when no packet has been heard", () => {
    expect(tncStatus(tncState({ stats: { ...tncState().stats, packets: 0, last_packet: null } }), NOW)).toBe("No packet yet");
  });

  it("says it is searching for the radio instead of listing the ports", () => {
    expect(tncStatus(searching(), NOW)).toBe("Searching for the radio…");
  });

  it("says since when a silent radio has said nothing", () => {
    expect(tncStatus(tncState({ state: "silent", silent_since: ago(7 * 60) }), NOW)).toMatch(/^nothing heard since \d\d:\d\d \(7 min\)$/);
  });

  it("says why it is not connected: the problem, else the last error, else nothing more", () => {
    expect(tncStatus(tncState({ state: "waiting", problem: "no KISS frames", last_error: "busy" }), NOW)).toBe("Not connected: no KISS frames");
    expect(tncStatus(tncState({ state: "waiting", last_error: "busy" }), NOW)).toBe("Not connected: busy");
    expect(tncStatus(tncState({ state: "stopped" }), NOW)).toBe("Not connected");
  });

  it("says what it is connecting to", () => {
    expect(tncStatus(tncState({ state: "connecting" }), NOW)).toBe("Connecting to /dev/brainbox_3…");
    expect(tncStatus(tncState({ state: "connecting", path: "" }), NOW)).toBe("Connecting…");
  });
});

describe("tncCounts", () => {
  it("says how much came in and went out, for the hover title of the line", () => {
    expect(tncCounts(tncState())).toBe("11 packets heard, 2.0 kB in, 0 B out, 0 digipeated");
    expect(tncCounts(tncState({ stats: { ...tncState().stats, packets: 1 } }))).toContain("1 packet heard");
  });
});

describe("searchedPorts", () => {
  it("lists the ports the daemon listens to while it searches", () => {
    expect(searchedPorts(searching())).toEqual(["/dev/ttyUSB0", "/dev/serial/by-id/usb-X-if00"]);
  });

  it("is null when a port is open or the line says something else", () => {
    expect(searchedPorts(tncState())).toBeNull();
    expect(searchedPorts(tncState({ path: "", describe: "socket://127.0.0.1:8001, waiting" }))).toBeNull();
  });
});

describe("localLine", () => {
  it("shows the time of a log line, which the daemon writes in UTC, in the viewer's time", () => {
    const at = new Date(NOW - 10_000).toISOString();
    const utc = at.slice(11, 19);
    expect(localLine(`${utc} NeoAPRS: opened /dev/x`, NOW)).toBe(`${clockText(at)} NeoAPRS: opened /dev/x`);
  });

  it("takes a time that has not come yet today for one of yesterday", () => {
    const later = new Date(NOW + 3_600_000);
    const line = `${later.toISOString().slice(11, 19)} text`;
    expect(localLine(line, NOW)).toBe(`${clockText(new Date(later.getTime() - 86_400_000).toISOString())} text`);
  });

  it("leaves a line without a time as it is", () => {
    expect(localLine("no time here", NOW)).toBe("no time here");
  });
});
