import { afterEach, describe, expect, it } from "vitest";
import { TOGETHER, confirmMessage, linkedValues, refusalFor, refusedAtField, remotePage, togetherOf } from "@/lib/settinglinks";
import { pairProblems, problemOf, sameValue } from "@/lib/fieldcheck";
import { reasonOf } from "@/lib/settings";
import { openedAt, resetSeen } from "@/test/fakealert";
import { errorOf } from "@/test/fixtures";

afterEach(() => resetSeen());

describe("problemOf", () => {
  it("has nothing against a value the daemon takes, and says what is wrong with one it would refuse", () => {
    expect(problemOf("station/call", "")).toBe("");
    expect(problemOf("station/call", "oh2gba-9")).toBe("");
    expect(problemOf("station/call", "OH2G BA")).toBe("Not a call");
    expect(problemOf("station/call", "N0CALL")).toBe("N0CALL is not a call");
    expect(problemOf("station/lat", "60,17")).toBe("");
    expect(problemOf("station/lat", "abc")).toBe("Not a number");
    expect(problemOf("station/lon", "181")).toBe("Between -180 and 180");
    expect(problemOf("map/radius_km", "5")).toBe("10 to 1000");
    expect(problemOf("status/interval_min", "7")).toBe(""); // (a choice of the page: the daemon is the judge of a stored one)
    expect(problemOf("beacon/interval_min", "7")).toBe(""); // (a choice of the page: the daemon is the judge of a stored one)
    expect(problemOf("serial/baud", "")).toBe("");
    expect(problemOf("serial/baud", "12")).toBe("300 to 921600");
    expect(problemOf("tcp/port", "")).toBe("1 to 65535");
    expect(problemOf("tcp/host", "a b")).toBe("Not an address");
    expect(problemOf("beacon/path", "WIDE1-1,WIDE2-1")).toBe("");
    expect(problemOf("beacon/path", "WIDE1-1,,TOOLONGCALL")).not.toBe("");
    expect(problemOf("station/comment", "anything")).toBe("");
  });

  it("knows a value is the one in force however it is written", () => {
    expect(sameValue("station/lat", "60.170", "60.17")).toBe(true);
    expect(sameValue("station/call", "oh2gba", "OH2GBA")).toBe(true);
    expect(sameValue("map/radius_km", "150 ", "150")).toBe(true);
    expect(sameValue("station/comment", "a", "A")).toBe(false);
    expect(sameValue("station/lat", "abc", "60.17")).toBe(false);
  });
});

describe("pairProblems", () => {
  const keys = ["station/lat", "station/lon"];
  it("wants both of a position or neither", () => {
    expect(pairProblems(keys, { "station/lat": "60", "station/lon": "24" })).toEqual({});
    expect(pairProblems(keys, { "station/lat": "", "station/lon": " " })).toEqual({});
    expect(pairProblems(keys, { "station/lat": "60", "station/lon": "" })).toEqual({ "station/lon": "Needed with the latitude" });
    expect(pairProblems(keys, { "station/lat": "", "station/lon": "24" })).toEqual({ "station/lat": "Needed with the longitude" });
    expect(pairProblems(["tcp/host", "tcp/port"], { "tcp/host": "a" })).toEqual({});
  });
});

describe("settinglinks", () => {
  it("lets the position go together", () => {
    expect(TOGETHER["station/lat"]).toEqual(["station/lat", "station/lon"]);
    expect(TOGETHER["station/comment"]).toBeUndefined();
  });

  it("shows the refusal of a setting under its field and in no toast", () => {
    expect(refusedAtField({ cmd: "set_config" })).toBe(true);
    expect(refusedAtField({ cmd: "qru_ask" })).toBe(true);
    expect(refusedAtField({ cmd: "send_message" })).toBe(false);
    expect(refusedAtField(null)).toBe(false);
  });

  it("links the rigctld to the radio as the status", () => {
    expect(linkedValues("status/source", "rig", {})).toEqual({ "status/rigctld": "127.0.0.1:4532" });
    expect(linkedValues("status/source", "rig", { "status/rigctld": "10.0.0.1:4532" })).toEqual({});
    expect(linkedValues("status/source", "text", {})).toEqual({});
  });

  it("puts a refusal under the key that was changed, or the one that explains it", () => {
    const comment = errorOf(
      "set_config: station/comment: 40 characters is more than the 36 allowed with the PHG extension (clear beacon/power_w to send none)",
      "setting.comment_too_long",
      { length: 40, limit: 36 },
    );
    expect(
      refusalFor(errorOf("set_config: station/lat: 95 is out", "setting.range", { value: 95, min: -90, max: 90 }), ["station/lat", "station/lon"]),
    ).toEqual({
      key: "station/lat",
      reason: "95 is not between -90 and 90",
    });
    expect(refusalFor(comment, ["beacon/power_w"])).toEqual({ key: "beacon/power_w", reason: "Shorten the comment to 36 first" });
    expect(refusalFor(errorOf("set_config: status/source: needs it", "setting.status_needs_rigctld"), ["status/rigctld"])).toEqual({
      key: "status/rigctld",
      reason: "the radio needs status/rigctld (host:port of a rigctld, 127.0.0.1:4532)",
    });
    expect(refusalFor(errorOf("set_config: the settings could not be stored", "setting.not_stored"), ["digi/enabled"])).toEqual({
      key: "digi/enabled",
      reason: "the settings could not be stored (the database would not take them); nothing changed",
    });
    expect(refusalFor(errorOf("set_config: serial/baud: x", "setting.not_whole", { value: "x" }), ["map/radius_km"])).toEqual({
      key: "map/radius_km",
      reason: "'x' is not a whole number",
    });
    expect(refusalFor({ ...comment, code: "other", params: {} }, ["beacon/power_w"]).reason, "without a code: the plain words, never the English").toBe(
      reasonOf({ ...comment, code: "other", params: {} }),
    );
  });

  it("asks only for what would cut the device off, and only on another device", () => {
    expect(confirmMessage("web/network", "false", true)).toBe("This device will lose the page. Turn off?");
    expect(confirmMessage("web/network", "true", true)).toBeNull();
    expect(confirmMessage("web/network", "false", false)).toBeNull();
    expect(confirmMessage("web/https", "true", true)).toBe("This device will lose the page. Turn on?");
    expect(confirmMessage("web/https", "false", true)).toBe("This device will lose the page. Turn off?");
    expect(confirmMessage("digi/enabled", "false", true)).toBeNull();
  });

  it("knows a page opened from another device", () => {
    expect(remotePage()).toBe(false);
    openedAt("192.168.1.20");
    expect(remotePage()).toBe(true);
    openedAt("localhost");
    expect(remotePage()).toBe(false);
  });
});

describe("the fields a radio's type sends together", () => {
  it("are a radio's host and TCP port, by its own keys; the others alone, and the station's pairs as they are", () => {
    expect(togetherOf("radio/5/tcp_host")).toEqual(["radio/5/tcp_host", "radio/5/tcp_port"]);
    expect(togetherOf("radio/5/tcp_port")).toEqual(["radio/5/tcp_host", "radio/5/tcp_port"]);
    expect(togetherOf("radio/3/port")).toEqual(["radio/3/port"]);
    expect(togetherOf("station/lat")).toBe(TOGETHER["station/lat"]);
    expect(togetherOf("station/call")).toEqual(["station/call"]);
  });

  it("has the refusal of a change of a radio said under its field, not in the toast", () => {
    expect(refusedAtField(errorOf("radio_change: the name 'X' is another radio's already"))).toBe(true);
    expect(refusedAtField(errorOf("radio_remove: there is no radio 9"))).toBe(false);
    expect(refusedAtField(errorOf("radio_add: the radio could not be stored"))).toBe(false);
  });
});
