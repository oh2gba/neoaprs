import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import { useSetupGuide } from "@/composables/useSetupGuide";
import type { Command, ConfigValues, PortsMessage } from "@/protocol/protocol";
import { configValues, toastOf } from "@/test/fixtures";

const fresh = (extra: Record<string, string> = {}) =>
  configValues({ "station/call": "", "station/lat": "", "station/lon": "", "serial/baud": "", "serial/port": "", ...extra });
const ports = (extra: Partial<PortsMessage> = {}): PortsMessage => ({
  type: "ports",
  search: true,
  ports: [{ device: "/dev/ttyUSB0", description: "FT232R USB UART", hwid: "n/a", vid: null, pid: null }],
  ...extra,
});

function setUp(initial: ConfigValues | null = fresh()) {
  const config = ref<ConfigValues | null>(initial);
  const lastError = ref<Toast | null>(null);
  const portList = ref<PortsMessage | null>(null);
  const sent: Command[] = [];
  const send = vi.fn((command: Command) => (sent.push(command), true));
  const guide = useSetupGuide(config, lastError, portList, send);
  /** The daemon tells the settings again, as it does after a save. */
  const told = async (extra: Record<string, string> = {}) => {
    const now = config.value ?? fresh();
    config.value = { values: { ...now.values, ...extra }, defaults: now.defaults, urls: now.urls, https: now.https };
    await nextTick();
  };
  const fail = async (text: string) => {
    lastError.value = toastOf(text, "other", {}, (lastError.value?.n ?? 0) + 1);
    await nextTick();
  };
  /** The first four steps answered. */
  const fill = (extra: Record<string, string> = {}) => {
    guide.edit("call", extra.call ?? "oh2abc");
    guide.edit("lat", "60.17");
    guide.edit("lon", "24.94");
  };
  return { guide, config, lastError, portList, sent, send, told, fail, fill };
}
const setConfigs = (sent: Command[]) => sent.filter((c) => c.cmd === "set_config");

describe("useSetupGuide: the steps", () => {
  it("starts closed on the first step, with the daemon's settings as the answers", () => {
    const { guide } = setUp();
    expect(guide.open).toBe(false);
    expect(guide.step).toBe(0);
    expect(guide.fields).toMatchObject({ call: "", lat: "", lon: "", symbol: "/-", profile: "kenwood-tnc2", radius: "150" });
    expect(guide.valid).toEqual([false, false, true, true, true]);
  });

  it("checks the call as it is typed and does not go on from a wrong one", () => {
    const { guide } = setUp();
    guide.edit("call", "n0call");
    expect(guide.problems.call).toBe("N0CALL is not a call");
    guide.next();
    expect(guide.step).toBe(0);
    guide.edit("call", "oh2abc-99");
    expect(guide.problems.call).toBe("Not a call");
    guide.edit("call", "oh2abc-9");
    expect(guide.problems.call).toBeUndefined();
    guide.next();
    expect(guide.step).toBe(1);
  });

  it("checks the position, and needs both numbers", () => {
    const { guide } = setUp();
    guide.edit("call", "oh2abc");
    guide.next();
    guide.edit("lat", "95");
    guide.edit("lon", "24.94");
    expect(guide.problems.lat).toBe("Between -90 and 90");
    guide.next();
    expect(guide.step).toBe(1);
    guide.edit("lat", "60.17");
    guide.edit("lon", "");
    guide.next();
    expect(guide.step).toBe(1);
    guide.edit("lon", "24,94");
    guide.next();
    expect(guide.step).toBe(2);
  });

  it("takes the centre of a locator of 6 characters, and writes the locator of a position", () => {
    const { guide } = setUp();
    guide.edit("locator", "KP20ie");
    expect(guide.fields.lat).toBe("60.1875");
    expect(guide.fields.lon).toBe("24.7083");
    expect(guide.fields.locator).toBe("KP20ie"); // as typed
    guide.edit("locator", "KP20");
    expect(guide.fields.lat).toBe("60.5");
    guide.edit("lat", "60.17");
    guide.edit("lon", "24.94");
    expect(guide.fields.locator).toBe("KP20le");
    guide.edit("locator", "SS00aa");
    expect(guide.problems.locator).toBe("Not a locator");
    guide.edit("locator", "KP20iezz");
    expect(guide.problems.locator).toBe("Not a locator");
    guide.edit("locator", "KP20i");
    expect(guide.problems.locator).toBeUndefined(); // still being typed
    guide.edit("lat", "x");
    expect(guide.fields.locator).toBe("");
  });

  it("takes a place from the map: five decimals, the longitude within -180 to 180, the marker where it is", () => {
    const { guide } = setUp();
    guide.place(60.1699999, 24.9400001);
    expect(guide.fields).toMatchObject({ lat: "60.17", lon: "24.94", locator: "KP20le" });
    expect(guide.pin).toEqual({ lat: 60.17, lon: 24.94 });
    guide.place(-33.123456789, 190.5);
    expect(guide.fields).toMatchObject({ lat: "-33.12346", lon: "-169.5" });
    guide.place(10, -190);
    expect(guide.fields.lon).toBe("170");
  });

  it("asks the map for a click on the position step only, while open", () => {
    const { guide } = setUp();
    expect(guide.picking).toBe(false);
    guide.show();
    expect(guide.picking).toBe(false);
    guide.edit("call", "oh2abc");
    guide.next();
    expect(guide.step).toBe(1);
    expect(guide.picking).toBe(true);
    guide.close();
    expect(guide.picking).toBe(false);
  });

  it("checks the symbol, the radio and the map", () => {
    const { guide, fill } = setUp();
    fill();
    guide.go(2);
    guide.edit("symbol", "a-");
    expect(guide.problems.symbol).toBe("Table: / \\ 0-9 A-Z");
    expect(guide.valid[2]).toBe(false);
    guide.edit("symbol", "\\k");
    guide.go(3);
    expect(guide.step).toBe(3);
    guide.edit("baud", "12");
    expect(guide.problems.baud).toBe("300 to 921600");
    guide.edit("baud", "");
    guide.edit("profile", "kiss-tcp");
    guide.edit("tcpPort", "99999");
    expect(guide.problems.tcpPort).toBe("1 to 65535");
    guide.edit("tcpPort", "8001");
    guide.go(4);
    guide.edit("radius", "5");
    expect(guide.problems.radius).toBe("10 to 1000");
    expect(guide.valid[4]).toBe(false);
  });

  it("goes back freely, goes forward only over steps that have what they need, and remembers the answers", () => {
    const { guide, fill } = setUp();
    guide.go(3);
    expect(guide.step).toBe(0);
    fill();
    guide.go(3);
    expect(guide.step).toBe(3);
    guide.edit("baud", "4800");
    guide.back();
    guide.back();
    expect(guide.step).toBe(1);
    guide.go(0);
    guide.edit("call", "");
    guide.go(2);
    expect(guide.step).toBe(0);
    guide.edit("call", "oh2abc");
    guide.go(3);
    expect(guide.fields.baud).toBe("4800");
  });

  it("keeps the answers when it is closed and opened again", () => {
    const { guide, fill } = setUp();
    guide.show();
    fill();
    guide.next();
    guide.next();
    guide.close();
    expect(guide.open).toBe(false);
    guide.show();
    expect(guide.step).toBe(2);
    expect(guide.fields.call).toBe("oh2abc");
  });
});

describe("useSetupGuide: the radio", () => {
  it("asks for the ports when the radio step is reached with a serial TNC, and again on Refresh", async () => {
    const { guide, sent, fill } = setUp();
    guide.show();
    fill();
    guide.go(3);
    await nextTick();
    expect(sent.filter((c) => c.cmd === "list_ports")).toHaveLength(1);
    guide.refreshPorts();
    expect(sent.filter((c) => c.cmd === "list_ports")).toHaveLength(2);
  });

  it("does not ask for ports for a TCP TNC, and asks when the TNC becomes a serial one", async () => {
    const { guide, sent, fill } = setUp(fresh({ "tnc/profile": "kiss-tcp" }));
    guide.show();
    fill();
    guide.go(3);
    await nextTick();
    expect(sent.filter((c) => c.cmd === "list_ports")).toHaveLength(0);
    guide.edit("profile", "kiss");
    await nextTick();
    expect(sent.filter((c) => c.cmd === "list_ports")).toHaveLength(1);
  });

  it("does not ask while the guide is closed or on another step", async () => {
    const { guide, sent, fill } = setUp();
    fill();
    guide.go(3);
    await nextTick();
    expect(sent).toEqual([]);
    guide.show();
    await nextTick();
    expect(sent).toEqual([{ cmd: "list_ports" }]); // open on the radio step
    guide.go(1);
    await nextTick();
    expect(sent).toEqual([{ cmd: "list_ports" }]);
  });

  it("needs the port picked where the daemon does not search, and takes Automatic (empty) where it does", async () => {
    const { guide, portList, fill } = setUp();
    fill();
    guide.go(3);
    portList.value = ports({ search: false });
    await nextTick();
    expect(guide.search).toBe(false);
    expect(guide.valid[3]).toBe(false);
    guide.edit("port", "/dev/ttyUSB0");
    expect(guide.valid[3]).toBe(true);
    guide.edit("port", "");
    portList.value = ports({ search: true });
    await nextTick();
    expect(guide.valid[3]).toBe(true);
  });
});

describe("useSetupGuide: Finish", () => {
  it("sends one set_config with exactly the keys that changed, and closes when the daemon tells the settings", async () => {
    const { guide, sent, told, fill } = setUp();
    guide.show();
    fill();
    guide.edit("symbol", "/>");
    guide.go(3);
    guide.edit("profile", "kantronics");
    guide.edit("port", "/dev/ttyUSB0");
    guide.edit("baud", "4800");
    guide.go(4);
    guide.edit("radius", "200");
    expect(guide.changes).toEqual({
      "station/call": "OH2ABC",
      "station/lat": "60.17",
      "station/lon": "24.94",
      "station/symbol_code": ">",
      "tnc/profile": "kantronics",
      "serial/port": "/dev/ttyUSB0",
      "serial/baud": "4800",
      "map/radius_km": "200",
      "beacon/interval_min": "30",
    });
    guide.next();
    expect(setConfigs(sent)).toEqual([{ cmd: "set_config", values: guide.changes }]);
    expect(sent.filter((c) => c.cmd !== "list_ports")).toHaveLength(1);
    expect(guide.saving).toBe(true);
    expect(guide.open).toBe(true);
    await told({ "station/call": "OH2ABC", "station/lat": "60.17" });
    expect(guide.saving).toBe(false);
    expect(guide.open).toBe(false);
    expect(guide.step).toBe(0);
    expect(setConfigs(sent)).toHaveLength(1);
  });

  it("sends only the changed keys: a fresh install that keeps the defaults sends the call and the position", () => {
    const { guide, sent, fill } = setUp();
    guide.show();
    fill();
    guide.go(4);
    guide.next();
    expect(setConfigs(sent)).toEqual([
      { cmd: "set_config", values: { "station/call": "OH2ABC", "station/lat": "60.17", "station/lon": "24.94", "beacon/interval_min": "30" } },
    ]);
  });

  it("sends nothing when nothing changed, and closes", () => {
    const { guide, sent } = setUp(configValues());
    guide.show();
    guide.go(4);
    expect(guide.step).toBe(4);
    guide.next();
    expect(sent).toEqual([]);
    expect(guide.open).toBe(false);
  });

  it("sends the TCP keys for a TCP TNC and clears the serial device", () => {
    const { guide, sent, fill } = setUp(fresh({ "serial/port": "/dev/ttyUSB0" }));
    guide.show();
    fill();
    guide.go(3);
    guide.edit("profile", "kiss-tcp");
    guide.edit("host", "192.168.1.5");
    guide.edit("tcpPort", "8002");
    guide.go(4);
    guide.next();
    expect(setConfigs(sent)[0]).toEqual({
      cmd: "set_config",
      values: {
        "station/call": "OH2ABC",
        "station/lat": "60.17",
        "station/lon": "24.94",
        "tnc/profile": "kiss-tcp",
        "tcp/host": "192.168.1.5",
        "tcp/port": "8002",
        "serial/port": "",
        "beacon/interval_min": "30",
      },
    });
  });

  it("does not send twice while the daemon has not answered", () => {
    const { guide, sent, fill } = setUp();
    guide.show();
    fill();
    guide.go(4);
    guide.next();
    guide.finish();
    guide.next();
    expect(setConfigs(sent)).toHaveLength(1);
  });

  it("will not finish with a step that is not right: it goes to the first such step", () => {
    const { guide, sent, fill } = setUp();
    fill();
    guide.go(4);
    guide.edit("call", "n0call");
    guide.finish();
    expect(sent).toEqual([]);
    expect(guide.step).toBe(0);
  });

  it("shows the daemon's complaint under the field it names, goes to its step, and sends again when it is put right", async () => {
    const { guide, sent, fail, fill } = setUp();
    guide.show();
    fill();
    guide.go(4);
    guide.next();
    expect(guide.saving).toBe(true);
    await fail("set_config: station/lat: 95 is not between -90 and 90");
    expect(guide.saving).toBe(false);
    expect(guide.open).toBe(true);
    expect(guide.step).toBe(1);
    expect(guide.problems.lat).toBe("95 is not between -90 and 90");
    guide.edit("lat", "60.17");
    expect(guide.problems.lat).toBeUndefined();
    guide.go(4);
    guide.next();
    expect(setConfigs(sent)).toHaveLength(2);
  });

  it("shows a complaint about the symbol under the symbol field, and one about a port on the radio step", async () => {
    const { guide, fail, fill } = setUp();
    guide.show();
    fill();
    guide.go(4);
    guide.next();
    await fail("set_config: station/symbol_table: '!' is not / or \\ or an overlay character A-Z, 0-9");
    expect(guide.step).toBe(2);
    expect(guide.problems.symbol).toContain("is not / or");
    guide.edit("symbol", "/-");
    guide.go(4);
    guide.next();
    await fail("set_config: serial/port: no such port");
    expect(guide.step).toBe(3);
    expect(guide.problems.port).toBe("no such port");
  });

  it("ignores an error it is not waiting for, and one that names no field of the guide", async () => {
    const { guide, fail, fill } = setUp();
    guide.show();
    fill();
    await fail("set_config: station/lat: 95 is not between -90 and 90");
    expect(guide.problems.lat).toBeUndefined();
    guide.go(4);
    guide.next();
    await fail("Not connected to the daemon.");
    expect(guide.saving).toBe(false);
    expect(Object.keys(guide.problems)).toEqual([]);
  });

  it("does not send when the socket is not open, so it is not left saving", () => {
    const { guide, send, fill } = setUp();
    send.mockReturnValue(false);
    guide.show();
    fill();
    guide.go(4);
    guide.next();
    expect(guide.saving).toBe(false);
  });
});

describe("useSetupGuide: the map step", () => {
  it("sends the map command at once when there is nothing to save", () => {
    const { guide, sent } = setUp(configValues());
    expect(guide.sendMap({ cmd: "map_estimate" })).toBe(true);
    expect(sent).toEqual([{ cmd: "map_estimate" }]);
  });

  it("saves what changed first, then sends the command when the daemon has told the settings: one set_config", async () => {
    const { guide, sent, told, fill } = setUp();
    guide.show();
    fill();
    guide.go(4);
    guide.sendMap({ cmd: "map_fetch" });
    expect(sent.filter((c) => c.cmd === "map_fetch")).toEqual([]);
    expect(setConfigs(sent)).toHaveLength(1);
    await told({ "station/call": "OH2ABC", "station/lat": "60.17", "station/lon": "24.94" });
    expect(sent.at(-1)).toEqual({ cmd: "map_fetch" });
    expect(guide.open).toBe(true); // not finished
    guide.next(); // Finish: nothing is left to save
    expect(setConfigs(sent)).toHaveLength(1);
    expect(guide.open).toBe(false);
  });

  it("drops the command and shows the complaint when the daemon refuses the save", async () => {
    const { guide, sent, fail, fill } = setUp();
    guide.show();
    fill();
    guide.go(4);
    guide.sendMap({ cmd: "map_estimate" });
    await fail("set_config: station/call: 'OH2ABC' is taken");
    expect(guide.problems.call).toBe("'OH2ABC' is taken");
    expect(sent.filter((c) => c.cmd === "map_estimate")).toEqual([]);
  });

  it("passes other commands on, and does not save again while a save is out", () => {
    const { guide, sent, fill } = setUp();
    fill();
    guide.go(4);
    expect(guide.sendMap({ cmd: "map_cancel" })).toBe(true);
    guide.sendMap({ cmd: "map_estimate" });
    expect(guide.sendMap({ cmd: "map_estimate" })).toBe(false);
    expect(setConfigs(sent)).toHaveLength(1);
  });
});

describe("useSetupGuide: the daemon's settings", () => {
  it("follows the settings while nothing is answered, and keeps the answers once one is", async () => {
    const { guide, told } = setUp();
    await told({ "station/call": "OH2XYZ", "station/lat": "61", "station/lon": "25" });
    expect(guide.fields).toMatchObject({ call: "OH2XYZ", lat: "61", lon: "25", locator: "KP21ma" });
    guide.edit("call", "oh2abc");
    await told({ "station/lat": "62" });
    expect(guide.fields).toMatchObject({ call: "oh2abc", lat: "61" });
  });

  it("fills the answers when the settings first arrive, and not over an answer afterwards", async () => {
    const { guide, config, told } = setUp(null);
    expect(guide.fields.call).toBe("");
    config.value = configValues({ "station/call": "OH2XYZ" });
    await nextTick();
    expect(guide.fields.call).toBe("OH2XYZ");
    guide.edit("call", "oh2abc");
    await told({ "station/lat": "61" });
    expect(guide.fields.call).toBe("oh2abc");
  });
});
