import { describe, expect, it } from "vitest";
import { isLoopbackHost, notificationTitle, scan } from "@/lib/pagealert";
import { incoming, message } from "@/test/fixtures";

describe("isLoopbackHost", () => {
  it("is true for the machine itself, in every spelling", () => {
    for (const host of ["localhost", "LOCALHOST", "127.0.0.1", "127.1.2.3", "[::1]", "::1", "neoaprs.localhost"]) expect(isLoopbackHost(host)).toBe(true);
  });

  it("is false for another device's view of the daemon", () => {
    for (const host of ["192.168.1.20", "raspberrypi.local", "pi.example.org", "127.0.0.1.example.org", "10.0.0.127", ""])
      expect(isLoopbackHost(host)).toBe(false);
  });
});

describe("scan", () => {
  it("alerts nothing the first time: the messages the page loaded with are the baseline", () => {
    const found = scan([incoming(3, "OH2RDG"), incoming(7, "OH2PU-9")], null);
    expect(found).toEqual({ mark: 7, fresh: [] });
  });

  it("gives the messages to us above the mark, the oldest first, and moves the mark", () => {
    const found = scan([incoming(9, "OH2PU-9"), incoming(3, "OH2RDG"), incoming(8, "OH2RDG")], 7);
    expect(found.fresh.map((m) => m.id)).toEqual([8, 9]);
    expect(found.mark).toBe(9);
  });

  it("leaves out the ones we overheard, the ones of ours and the ones it has told already", () => {
    const rows = [
      incoming(8, "OH2RDG", { state: "overheard", to_call: "OH2XYZ" }),
      message(9, { to_call: "OH2RDG" }),
      incoming(7, "OH2RDG"),
      incoming(10, "OH2PU-9"),
    ];
    const found = scan(rows, 7);
    expect(found.fresh.map((m) => m.id)).toEqual([10]);
    expect(found.mark).toBe(10);
  });

  it("does not move the mark back when the rows are fewer (a message deleted)", () => {
    expect(scan([incoming(2, "OH2RDG")], 7)).toEqual({ mark: 7, fresh: [] });
  });
});

it("names the sender in the notification", () => {
  expect(notificationTitle("OH2DPN")).toBe("APRS message from OH2DPN");
});
