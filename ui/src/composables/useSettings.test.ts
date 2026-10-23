import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { UNDO_MS } from "@/composables/useSettingsFeedback";
import { ANSWER_MS } from "@/composables/useSettingsQueue";
import { useSettings } from "@/composables/useSettings";
import type { Toast } from "@/composables/useDaemon";
import type { Command, ConfigValues } from "@/protocol/protocol";
import { configValues, toastOf } from "@/test/fixtures";

function setUp(extra: Record<string, string> = {}) {
  const config = ref<ConfigValues | null>(configValues(extra));
  const lastError = ref<Toast | null>(null);
  const send = vi.fn((_command: Command) => true);
  const settings = useSettings(config, lastError, send);
  let errors = 0;
  /** The daemon accepts the request in flight: it tells the settings again, with these values put in. */
  const answer = async (changes: Record<string, string> = {}) => {
    config.value = configValues({ ...config.value?.values, ...changes });
    await nextTick();
  };
  /** The daemon refuses the request in flight. */
  const refuse = async (text: string, code = "other", params: Record<string, string | number> = {}) => {
    lastError.value = toastOf(text, code, params, ++errors);
    await nextTick();
  };
  const sets = () => send.mock.calls.map(([command]) => (command as { values: Record<string, string> }).values);
  return { config, send, settings, answer, refuse, sets };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useSettings: when a change applies", () => {
  it("starts as the daemon's values and sends nothing", () => {
    const { settings, send } = setUp();
    expect(settings.draft["station/call"]).toBe("OH2GBA");
    expect(settings.saving.value).toBe(false);
    expect(send).not.toHaveBeenCalled();
  });

  it("sends a choice at once, with only the key that changed", () => {
    const { settings, sets } = setUp();
    settings.change({ "digi/enabled": "true" });
    expect(sets()).toEqual([{ "digi/enabled": "true" }]);
    expect(settings.saving.value).toBe(true);
  });

  it("sends nothing for a choice that is what it is", () => {
    const { settings, send } = setUp();
    settings.change({ "digi/enabled": "false" });
    expect(send).not.toHaveBeenCalled();
  });

  it("does not send a typed text while it is typed, only when it is committed", () => {
    const { settings, send, sets } = setUp();
    for (const text of ["N", "NE", "NEW", "NEWC"]) settings.edit("station/comment", text);
    expect(send).not.toHaveBeenCalled();
    settings.commit(["station/comment"]);
    expect(sets()).toEqual([{ "station/comment": "NEWC" }]);
  });

  it("never sends a text the page finds invalid, a half-typed call or a position out of range, and says why under the field", () => {
    const { settings, send } = setUp();
    settings.edit("station/call", "OH2G BA");
    settings.commit(["station/call"]);
    expect(settings.errors["station/call"]).toBe("Not a call");
    settings.edit("station/lat", "95");
    settings.commit(["station/lat"]);
    expect(settings.errors["station/lat"]).toBe("Between -90 and 90");
    settings.edit("map/radius_km", "5");
    settings.commit(["map/radius_km"]);
    expect(settings.errors["map/radius_km"]).toBe("10 to 1000");
    settings.edit("tcp/port", "");
    settings.commit(["tcp/port"]);
    expect(settings.errors["tcp/port"]).toBe("1 to 65535");
    expect(send).not.toHaveBeenCalled();
    expect(settings.saving.value).toBe(false);
    expect(settings.draft["station/lat"]).toBe("95");
  });

  it("does not send a value that is what the daemon has however it is written, and writes it the daemon's way", () => {
    const { settings, send } = setUp();
    settings.edit("station/lat", "60.170");
    settings.edit("station/call", "oh2gba");
    settings.commit(["station/lat", "station/call"]);
    expect(send).not.toHaveBeenCalled();
    expect(settings.draft["station/lat"]).toBe("60.17");
    expect(settings.draft["station/call"]).toBe("OH2GBA");
  });

  it("puts the value in force back on Esc, and takes the complaint away", () => {
    const { settings, send } = setUp();
    settings.edit("station/lat", "95");
    settings.commit(["station/lat"]);
    settings.cancel("station/lat");
    expect(settings.draft["station/lat"]).toBe("60.17");
    expect(settings.errors["station/lat"]).toBeUndefined();
    settings.edit("station/comment", "half typed");
    settings.cancel("station/comment");
    expect(settings.draft["station/comment"]).toBe("NeoAPRS");
    expect(send).not.toHaveBeenCalled();
  });

  it("sends the fields that belong together in one set_config", () => {
    const { settings, sets } = setUp();
    settings.change({ "station/lat": "61.5", "station/lon": "25.5" });
    settings.edit("tcp/host", "10.0.0.5");
    settings.edit("tcp/port", "8100");
    settings.commit(["tcp/host", "tcp/port"]);
    expect(sets()).toEqual([{ "station/lat": "61.5", "station/lon": "25.5" }]);
  });

  it("sends a pair with one invalid as nothing, and sends only the one that changed when the other is as it was", () => {
    const { settings, sets } = setUp();
    settings.edit("tcp/host", "10.0.0.5");
    settings.edit("tcp/port", "99999");
    settings.commit(["tcp/host", "tcp/port"]);
    expect(sets()).toEqual([]);
    expect(settings.errors["tcp/port"]).toBe("1 to 65535");
    settings.edit("tcp/port", "8001");
    settings.commit(["tcp/host", "tcp/port"]);
    expect(sets()).toEqual([{ "tcp/host": "10.0.0.5" }]);
  });
});

describe("useSettings: one save at a time", () => {
  it("keeps the next request until the one that is out has been answered, and sends them in order", async () => {
    const { settings, send, answer, sets } = setUp();
    settings.change({ "digi/enabled": "true" });
    settings.change({ "map/radius_km": "200" });
    settings.edit("station/comment", "third");
    settings.commit(["station/comment"]);
    expect(sets()).toEqual([{ "digi/enabled": "true" }]);
    await answer({ "digi/enabled": "true" });
    expect(sets()).toEqual([{ "digi/enabled": "true" }, { "map/radius_km": "200" }]);
    await answer({ "map/radius_km": "200" });
    expect(sets()[2]).toEqual({ "station/comment": "third" });
    await answer({ "station/comment": "third" });
    expect(send).toHaveBeenCalledTimes(3);
    expect(settings.saving.value).toBe(false);
  });

  it("gives an answer to one request only: a refusal of the first does not stop the second", async () => {
    const { settings, refuse, answer, sets } = setUp();
    settings.change({ "map/source": "ftp://x.org/m.pmtiles" });
    settings.change({ "digi/enabled": "true" });
    await refuse("set_config: map/source: ftp://x.org/m.pmtiles is not an http or https address");
    expect(settings.errors["map/source"]).toBe("ftp://x.org/m.pmtiles is not an http or https address");
    expect(settings.errors["digi/enabled"]).toBeUndefined();
    expect(sets()).toEqual([{ "map/source": "ftp://x.org/m.pmtiles" }, { "digi/enabled": "true" }]);
    await answer({ "digi/enabled": "true" });
    expect(settings.errors["map/source"]).toBe("ftp://x.org/m.pmtiles is not an http or https address");
  });

  it("does not send what is already on its way twice (Enter, then leaving the field)", async () => {
    const { settings, sets, answer } = setUp();
    settings.edit("station/comment", "mine");
    settings.commit(["station/comment"]);
    settings.commit(["station/comment"]);
    expect(sets()).toHaveLength(1);
    await answer({ "station/comment": "mine" });
    settings.commit(["station/comment"]);
    expect(sets()).toHaveLength(1);
  });

  it("gives up a request the daemon does not answer, and goes on", () => {
    const { settings, sets } = setUp();
    settings.change({ "digi/enabled": "true" });
    settings.change({ "map/radius_km": "200" });
    vi.advanceTimersByTime(ANSWER_MS + 1);
    expect(settings.errors["digi/enabled"]).toBe("No answer from the daemon.");
    expect(sets()).toHaveLength(2);
  });

  it("says so under the field when the command could not be sent, and does not wait for an answer", () => {
    const config = ref<ConfigValues | null>(configValues());
    const settings = useSettings(config, ref(null), () => false);
    settings.change({ "digi/enabled": "true" });
    expect(settings.errors["digi/enabled"]).toContain("no connection");
    expect(settings.saving.value).toBe(false);
    expect(settings.draft["digi/enabled"]).toBe("false");
  });

  it("does not take an error of another command for the answer", async () => {
    const { settings, refuse } = setUp();
    settings.change({ "digi/enabled": "true" });
    await refuse("forget_station: call: is missing");
    expect(settings.saving.value).toBe(true);
    expect(Object.keys(settings.errors)).toEqual([]);
  });
});

describe("useSettings: the daemon's answer", () => {
  it("tells a screen reader Saved when the settings come back, and takes the value the way the daemon writes it", async () => {
    const { settings, answer } = setUp();
    settings.edit("station/call", "oh2gba-9");
    settings.commit(["station/call"]);
    await answer({ "station/call": "OH2GBA-9" });
    expect(settings.draft["station/call"]).toBe("OH2GBA-9");
    expect(settings.announcement.value.text).toBe("Saved");
  });

  it("shows the refusal under the key it names, keeps the typed text, and leaves the old value in force", async () => {
    const { settings, refuse, config } = setUp();
    settings.edit("station/lat", "89.5");
    settings.commit(["station/lat"]);
    await refuse("set_config: station/lat: 89.5 is not between -90 and 90");
    expect(settings.errors["station/lat"]).toBe("89.5 is not between -90 and 90");
    expect(settings.draft["station/lat"]).toBe("89.5");
    expect(config.value?.values["station/lat"]).toBe("60.17");
    expect(settings.saving.value).toBe(false);
    settings.edit("station/lat", "60");
    expect(settings.errors["station/lat"]).toBeUndefined();
  });

  it("shows a refused choice as it was, with the reason under it", async () => {
    const { settings, refuse } = setUp();
    settings.change({ "tnc/profile": "kiss" });
    await refuse("set_config: tnc/profile: KISS TNC does not go with this port");
    expect(settings.errors["tnc/profile"]).toBe("KISS TNC does not go with this port");
    expect(settings.draft["tnc/profile"]).toBe("kenwood-tnc2");
  });

  it("follows the daemon for a field that was not touched, and leaves one that is being edited alone", async () => {
    const { settings, answer } = setUp();
    settings.edit("station/comment", "mine");
    await answer({ "station/comment": "theirs", "serial/baud": "4800" });
    expect(settings.draft["station/comment"]).toBe("mine");
    expect(settings.draft["serial/baud"]).toBe("4800");
  });

  it("keeps a field that waits in the queue as it was asked for", async () => {
    const { settings, answer } = setUp();
    settings.change({ "digi/enabled": "true" });
    settings.change({ "map/radius_km": "200" });
    await answer({ "digi/enabled": "true", "map/radius_km": "150" });
    expect(settings.draft["map/radius_km"]).toBe("200");
  });
});

describe("useSettings: linked rules", () => {
  it("fills in the usual rigctld with the choice of the radio as the status, so that the choice is valid at once", () => {
    const { settings, sets } = setUp();
    settings.change({ "status/source": "rig" });
    expect(sets()).toEqual([{ "status/source": "rig", "status/rigctld": "127.0.0.1:4532" }]);
    expect(settings.draft["status/rigctld"]).toBe("127.0.0.1:4532");
  });

  it("leaves a rigctld that is there alone", () => {
    const { settings, sets } = setUp({ "status/rigctld": "10.0.0.2:4533", "status/source": "text" });
    settings.change({ "status/source": "rig" });
    expect(sets()).toEqual([{ "status/source": "rig" }]);
  });

  it("clears a serial device when a TCP radio type is chosen, and keeps an address", () => {
    const serial = setUp({ "serial/port": "/dev/ttyUSB0" });
    serial.settings.change({ "tnc/profile": "kiss-tcp" });
    expect(serial.sets()).toEqual([{ "tnc/profile": "kiss-tcp", "serial/port": "" }]);
    const address = setUp({ "serial/port": "tcp://10.0.0.5:8100" });
    address.settings.change({ "tnc/profile": "kiss-tcp" });
    expect(address.sets()).toEqual([{ "tnc/profile": "kiss-tcp" }]);
  });

  it("shows a comment too long for the power just set under the power, and says what to do", async () => {
    const { settings, refuse } = setUp({ "station/comment": "x".repeat(40) });
    settings.edit("beacon/power_w", "5");
    settings.commit(["beacon/power_w"]);
    await refuse(
      "set_config: station/comment: 40 characters is more than the 36 allowed with the PHG extension (clear beacon/power_w to send none)",
      "setting.comment_too_long",
      { length: 40, limit: 36 },
    );
    expect(settings.errors["beacon/power_w"]).toBe("Shorten the comment to 36 first");
    expect(settings.errors["station/comment"]).toBeUndefined();
    expect(settings.draft["beacon/power_w"]).toBe("5");
  });

  it("shows the comment's own complaint under the comment when the comment was changed", async () => {
    const { settings, refuse } = setUp({ "beacon/power_w": "5" });
    settings.edit("station/comment", "x".repeat(40));
    settings.commit(["station/comment"]);
    await refuse(
      "set_config: station/comment: 40 characters is more than the 36 allowed with the PHG extension (clear beacon/power_w to send none)",
      "setting.comment_too_long",
      { length: 40, limit: 36 },
    );
    expect(settings.errors["station/comment"]).toContain("more than the 36 allowed");
  });

  it("shows the radio without a rigctld under the rigctld that was cleared", async () => {
    const { settings, refuse } = setUp({ "status/source": "rig", "status/rigctld": "127.0.0.1:4532" });
    settings.edit("status/rigctld", "");
    settings.commit(["status/rigctld"]);
    await refuse("set_config: status/source: the radio needs status/rigctld (host:port of a rigctld, 127.0.0.1:4532)");
    expect(settings.errors["status/rigctld"]).toContain("needs status/rigctld");
    expect(settings.errors["status/source"]).toBeUndefined();
  });
});

describe("useSettings: Undo", () => {
  it("offers to undo the change once it is saved, and sends the old values in one set_config", async () => {
    const { settings, answer, sets } = setUp();
    settings.edit("beacon/interval_min", "30");
    settings.commit(["beacon/interval_min"]);
    expect(settings.undo.value).toBeNull();
    await answer({ "beacon/interval_min": "30" });
    expect(settings.undo.value?.label).toBe("Beacon interval");
    expect(settings.undo.value?.values).toEqual({ "beacon/interval_min": "0" });
    settings.undoLast();
    expect(sets()[1]).toEqual({ "beacon/interval_min": "0" });
    expect(settings.draft["beacon/interval_min"]).toBe("0");
    expect(settings.undo.value).toBeNull();
    await answer({ "beacon/interval_min": "0" });
    expect(settings.undo.value).toBeNull(); // (an Undo is not undone in its turn)
  });

  it("puts back everything a change replaced, in one request", async () => {
    const { settings, answer, sets } = setUp();
    settings.change({ "status/source": "rig" });
    await answer({ "status/source": "rig", "status/rigctld": "127.0.0.1:4532" });
    settings.undoLast();
    expect(sets()[1]).toEqual({ "status/source": "", "status/rigctld": "" });
  });

  it("names a position changed together as one, and a symbol", async () => {
    const { settings, answer } = setUp();
    settings.change({ "station/lat": "61.5", "station/lon": "25.5" });
    await answer({ "station/lat": "61.5", "station/lon": "25.5" });
    expect(settings.undo.value?.label).toBe("Position");
    settings.change({ "station/symbol_table": "\\", "station/symbol_code": "#" });
    await answer({ "station/symbol_table": "\\", "station/symbol_code": "#" });
    expect(settings.undo.value?.label).toBe("Symbol");
  });

  it("covers the latest change only: earlier ones are just applied", async () => {
    const { settings, answer } = setUp();
    settings.change({ "digi/enabled": "true" });
    settings.change({ "map/radius_km": "200" });
    await answer({ "digi/enabled": "true" });
    expect(settings.undo.value).toBeNull(); // (another change is waiting behind it)
    await answer({ "map/radius_km": "200" });
    expect(settings.undo.value?.label).toBe("Map radius");
    settings.change({ "map/radius_km": "100" });
    expect(settings.undo.value).toBeNull();
  });

  it("goes after a few seconds, and offers nothing for a save that changed nothing", async () => {
    const { settings, answer } = setUp();
    settings.change({ "digi/enabled": "true" });
    await answer({ "digi/enabled": "true" });
    expect(settings.undo.value).not.toBeNull();
    vi.advanceTimersByTime(UNDO_MS + 1);
    expect(settings.undo.value).toBeNull();
    settings.edit("station/call", "OH2GBA-1");
    settings.commit(["station/call"]);
    await answer({ "station/call": "OH2GBA" }); // (the daemon would not have it)
    expect(settings.undo.value).toBeNull();
  });
});
