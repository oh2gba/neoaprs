import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { ANSWER_MS } from "@/composables/useSettingsQueue";
import { useSettings } from "@/composables/useSettings";
import type { Toast } from "@/composables/useDaemon";
import type { Command, ConfigValues } from "@/protocol/protocol";
import { configValues, toastOf } from "@/test/fixtures";
import { pairField } from "@/lib/settingspair";

function setUp(extra: Record<string, string> = {}) {
  const config = ref<ConfigValues | null>(configValues(extra));
  const lastError = ref<Toast | null>(null);
  const send = vi.fn((_command: Command) => true);
  const settings = useSettings(config, lastError, send);
  let errors = 0;
  /** The daemon accepts the request in flight: it tells the settings again, with these values put in. */
  const answer = async (changes: Record<string, string> = {}) => {
    const own = (radio: boolean) => Object.fromEntries(Object.entries(changes).filter(([key]) => key.startsWith("radio/") === radio));
    config.value = configValues({ ...config.value?.values, ...own(false) }, { ...config.value?.radio_values, ...own(true) });
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
    settings.change({ "radio/1/digipeat": "true" });
    expect(sets()).toEqual([{ "radio/1/digipeat": "true" }]);
    expect(settings.saving.value).toBe(true);
  });

  it("sends nothing for a choice that is what it is", () => {
    const { settings, send } = setUp();
    settings.change({ "radio/1/digipeat": "false" });
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
    expect(settings.errors["map/radius_km"]).toBe("10 to 300");
    settings.edit("radio/1/tcp_port", "");
    settings.commit(["radio/1/tcp_port"]);
    expect(settings.errors["radio/1/tcp_port"]).toBe("1 to 65535");
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
    settings.edit("radio/1/tcp_host", "10.0.0.5");
    settings.edit("radio/1/tcp_port", "8100");
    settings.commit(["radio/1/tcp_host", "radio/1/tcp_port"]);
    expect(sets()).toEqual([{ "station/lat": "61.5", "station/lon": "25.5" }]);
  });

  it("sends a pair with one invalid as nothing, and sends only the one that changed when the other is as it was", () => {
    const { settings, sets } = setUp();
    settings.edit("radio/1/tcp_host", "10.0.0.5");
    settings.edit("radio/1/tcp_port", "99999");
    settings.commit(["radio/1/tcp_host", "radio/1/tcp_port"]);
    expect(sets()).toEqual([]);
    expect(settings.errors["radio/1/tcp_port"]).toBe("1 to 65535");
    settings.edit("radio/1/tcp_port", "8001");
    settings.commit(["radio/1/tcp_host", "radio/1/tcp_port"]);
    expect(sets()).toEqual([{ "radio/1/tcp_host": "10.0.0.5" }]);
  });
});

describe("useSettings: one save at a time", () => {
  it("keeps the next request until the one that is out has been answered, and sends them in order", async () => {
    const { settings, send, answer, sets } = setUp();
    settings.change({ "radio/1/digipeat": "true" });
    settings.change({ "map/radius_km": "200" });
    settings.edit("station/comment", "third");
    settings.commit(["station/comment"]);
    expect(sets()).toEqual([{ "radio/1/digipeat": "true" }]);
    await answer({ "radio/1/digipeat": "true" });
    expect(sets()).toEqual([{ "radio/1/digipeat": "true" }, { "map/radius_km": "200" }]);
    await answer({ "map/radius_km": "200" });
    expect(sets()[2]).toEqual({ "station/comment": "third" });
    await answer({ "station/comment": "third" });
    expect(send).toHaveBeenCalledTimes(3);
    expect(settings.saving.value).toBe(false);
  });

  it("gives an answer to one request only: a refusal of the first does not stop the second", async () => {
    const { settings, refuse, answer, sets } = setUp();
    settings.change({ "map/source": "ftp://x.org/m.pmtiles" });
    settings.change({ "radio/1/digipeat": "true" });
    await refuse("set_config: map/source: 'ftp://x.org/m.pmtiles' is not a web address or the path of a PMTiles file", "setting.not_map_source", {
      value: "ftp://x.org/m.pmtiles",
    });
    expect(settings.errors["map/source"]).toBe("'ftp://x.org/m.pmtiles' is not a web address or the path of a PMTiles file");
    expect(settings.errors["radio/1/digipeat"]).toBeUndefined();
    expect(sets()).toEqual([{ "map/source": "ftp://x.org/m.pmtiles" }, { "radio/1/digipeat": "true" }]);
    await answer({ "radio/1/digipeat": "true" });
    expect(settings.errors["map/source"]).toBe("'ftp://x.org/m.pmtiles' is not a web address or the path of a PMTiles file");
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
    settings.change({ "radio/1/digipeat": "true" });
    settings.change({ "map/radius_km": "200" });
    vi.advanceTimersByTime(ANSWER_MS + 1);
    expect(settings.errors["radio/1/digipeat"]).toBe("No answer from NeoAPRS.");
    expect(sets()).toHaveLength(2);
  });

  it("says so under the field when the command could not be sent, and does not wait for an answer", () => {
    const config = ref<ConfigValues | null>(configValues());
    const settings = useSettings(config, ref(null), () => false);
    settings.change({ "radio/1/digipeat": "true" });
    expect(settings.errors["radio/1/digipeat"]).toContain("no connection");
    expect(settings.saving.value).toBe(false);
    expect(settings.draft["radio/1/digipeat"]).toBe("false");
  });

  it("does not take an error of another command for the answer", async () => {
    const { settings, refuse } = setUp();
    settings.change({ "radio/1/digipeat": "true" });
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
    await refuse("set_config: station/lat: 89.5 is not between -90 and 90", "setting.range", { value: 89.5, min: -90, max: 90 });
    expect(settings.errors["station/lat"]).toBe("89.5 is not between -90 and 90");
    expect(settings.draft["station/lat"]).toBe("89.5");
    expect(config.value?.values["station/lat"]).toBe("60.17");
    expect(settings.saving.value).toBe(false);
    settings.edit("station/lat", "60");
    expect(settings.errors["station/lat"]).toBeUndefined();
  });

  it("shows a refused choice as it was, with the reason under it", async () => {
    const { settings, refuse } = setUp();
    settings.change({ "gps/source": "serial" });
    await refuse("set_config: gps/source: the device is in use by the GPS receiver: choose another", "radio.resource_held", {
      resource: "gps",
      holder: "GPS",
      held_by: 0,
    });
    expect(settings.errors["gps/source"]).toBe("the device is in use by the GPS receiver: choose another");
    expect(settings.draft["gps/source"]).toBe("off");
  });

  it("follows the daemon for a field that was not touched, and leaves one that is being edited alone", async () => {
    const { settings, answer } = setUp();
    settings.edit("station/comment", "mine");
    await answer({ "station/comment": "theirs", "map/radius_km": "200" });
    expect(settings.draft["station/comment"]).toBe("mine");
    expect(settings.draft["map/radius_km"]).toBe("200");
  });

  it("keeps a field that waits in the queue as it was asked for", async () => {
    const { settings, answer } = setUp();
    settings.change({ "radio/1/digipeat": "true" });
    settings.change({ "map/radius_km": "200" });
    await answer({ "radio/1/digipeat": "true", "map/radius_km": "150" });
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
    await refuse("set_config: status/source: the radio needs status/rigctld (host:port of a rigctld, 127.0.0.1:4532)", "setting.status_needs_rigctld");
    expect(settings.errors["status/rigctld"]).toContain("needs status/rigctld");
    expect(settings.errors["status/source"]).toBeUndefined();
  });
});

describe("useSettings: no toast", () => {
  it("tells a screen reader that it was saved and offers nothing else: no Undo, no toast", async () => {
    const { settings, answer } = setUp();
    settings.edit("beacon/interval_min", "60");
    settings.commit(["beacon/interval_min"]);
    expect(settings.announcement.value.text).toBe("");
    await answer({ "beacon/interval_min": "60" });
    expect(settings.announcement.value.text).toBe("Saved");
    expect("undo" in settings || "undoLast" in settings).toBe(false);
  });
});

// The radios' own settings (`radio/3/port`) and the station's (`email/radio`), which the daemon tells apart in `config.radio_values`: the form works them as it works the others.
describe("useSettings: the radios' own settings", () => {
  const withOwn = (config: ConfigValues, own: Record<string, string>): ConfigValues => ({
    ...config,
    radio_values: { ...config.radio_values, ...own },
    radio_defaults: { ...config.radio_defaults, "radio/3/baud": "9600" },
  });

  it("are in the draft and the defaults beside the settings of before, and sent as any setting", () => {
    const { config, settings, sets } = setUp();
    config.value = withOwn(configValues(), { "radio/3/port": "/dev/ttyACM0", "radio/3/baud": "" });
    return nextTick().then(() => {
      expect([settings.draft["radio/3/port"], settings.draft["email/radio"], settings.draft["station/call"]]).toEqual(["/dev/ttyACM0", "", "OH2GBA"]);
      expect(settings.defaults.value["radio/3/baud"]).toBe("9600");
      settings.change({ "radio/3/port": "/dev/ttyUSB1" });
      expect(sets()).toEqual([{ "radio/3/port": "/dev/ttyUSB1" }]);
    });
  });

  it("follow the daemon where they were not touched, and keep a refusal under the key it names", async () => {
    const { config, settings, refuse } = setUp();
    config.value = withOwn(configValues(), { "radio/3/port": "/dev/ttyACM0", "radio/3/baud": "" });
    await nextTick();
    config.value = withOwn(configValues(), { "radio/3/port": "/dev/ttyACM1", "radio/3/baud": "" });
    await nextTick();
    expect(settings.draft["radio/3/port"]).toBe("/dev/ttyACM1");
    settings.change({ "radio/3/port": "/dev/ttyUSB0" });
    await refuse("set_config: radio/3/port: the device is in use by radio Mobile: choose another", "radio.resource_held", {
      resource: "serial",
      holder: "Mobile",
    });
    expect(settings.errors["radio/3/port"]).toBe("the device is in use by radio Mobile: choose another");
    expect(settings.draft["radio/3/port"]).toBe("/dev/ttyACM1");
  });
});

// A pair of radios' keys (`pair/1/3/enabled`) are told for the radios that are there: when the daemon stops telling them, the form stops counting the pair's call as taken.
describe("useSettings: the keys of a pair that is gone", () => {
  const both = { "pair/1/2/enabled": "true", "pair/1/2/ssid": "14", "pair/1/3/enabled": "true", "pair/1/3/ssid": "15" };
  const callsOf = (draft: Record<string, string>) =>
    pairField("pair/1/2/ssid", draft)?.choices?.map((choice) => (typeof choice === "string" ? choice : choice.value));

  it("leave the draft, and the call the pair held is free again", async () => {
    const { config, settings } = setUp();
    config.value = configValues(both);
    await nextTick();
    expect(callsOf(settings.draft)).not.toContain("15");
    config.value = configValues({ "pair/1/2/enabled": "true", "pair/1/2/ssid": "14" });
    await nextTick();
    expect(Object.keys(settings.draft).filter((key) => key.startsWith("pair/1/3/"))).toEqual([]);
    expect(callsOf(settings.draft)).toContain("15");
  });

  it("stay while one is edited or waits for its answer", async () => {
    const { config, settings } = setUp();
    config.value = configValues(both);
    await nextTick();
    settings.change({ "pair/1/3/ssid": "13" });
    config.value = configValues({ "pair/1/2/enabled": "true", "pair/1/2/ssid": "14" });
    await nextTick();
    expect(settings.draft["pair/1/3/ssid"]).toBe("13");
    expect(settings.draft["pair/1/3/enabled"]).toBeUndefined();
  });
});

describe("useSettings: a tell of the settings for another reason", () => {
  it("leaves a later refusal of the request it released at that request's field, and the next one waiting", async () => {
    const config = ref<ConfigValues | null>(configValues());
    const lastError = ref<Toast | null>(null);
    const send = vi.fn((_c: Command) => true);
    const settings = useSettings(config, lastError, send);
    settings.edit("station/comment", "Hello A");
    settings.commit(["station/comment"]);
    settings.edit("status/text", "Text B");
    settings.commit(["status/text"]);
    config.value = configValues({ ...config.value?.values, "web/key": "newkey" }); // (another device saved its own)
    await nextTick();
    expect(send).toHaveBeenCalledTimes(2);
    lastError.value = toastOf("set_config: station/comment: too long", "other", {}, 1);
    await nextTick();
    expect(settings.errors["station/comment"]).toBeDefined();
    expect(settings.errors["status/text"]).toBeUndefined();
    expect(settings.saving.value).toBe(true);
  });
});
