import { describe, expect, it } from "vitest";
import { clockText } from "@/lib/format";
import { localLine, searchedPorts, tncStatus } from "@/lib/tncstatus";
import { NOW, ago, tncState } from "@/test/fixtures";

const searching = () =>
  tncState({ state: "waiting", path: "", describe: "listening on /dev/ttyUSB0, /dev/serial/by-id/usb-X-if00 for the radio", stats: { ...tncState().stats, packets: 0 } });

describe("tncStatus", () => {
  it("says what it is connected to, how many packets it has heard and when the last one came", () => {
    const tnc = tncState({ path: "/dev/ttyUSB0", stats: { ...tncState().stats, packets: 412, last_packet: ago(120) } });
    expect(tncStatus(tnc, NOW)).toBe("Connected to /dev/ttyUSB0, 412 packets, last 2 min ago");
  });

  it("says so when no packet has been heard, and is right about one", () => {
    expect(tncStatus(tncState({ stats: { ...tncState().stats, packets: 0, last_packet: null } }), NOW)).toBe("Connected to /dev/brainbox_3, no packets yet");
    expect(tncStatus(tncState({ stats: { ...tncState().stats, packets: 1, last_packet: ago(5) } }), NOW)).toBe("Connected to /dev/brainbox_3, 1 packet, last 5 s ago");
  });

  it("says it is searching for the radio instead of listing the ports", () => {
    expect(tncStatus(searching(), NOW)).toBe("Searching for the radio…");
  });

  it("says since when a silent radio has said nothing", () => {
    expect(tncStatus(tncState({ state: "silent", silent_since: ago(7 * 60) }), NOW)).toMatch(/^nothing heard since \d\d:\d\d \(7 min\)$/);
  });

  it("says what it is waiting for, or trying", () => {
    expect(tncStatus(tncState({ state: "waiting" }), NOW)).toBe("Waiting for /dev/brainbox_3…");
    expect(tncStatus(tncState({ state: "waiting", path: "" }), NOW)).toBe("Waiting for the radio…");
    expect(tncStatus(tncState({ state: "connecting" }), NOW)).toBe("Connecting to /dev/brainbox_3…");
    expect(tncStatus(tncState({ state: "stopped" }), NOW)).toBe("Not connected");
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
