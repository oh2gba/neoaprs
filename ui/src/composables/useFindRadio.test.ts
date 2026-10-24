import { describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, shallowRef } from "vue";
import type { Toast } from "@/composables/useDaemon";
import { foundSettings, useFindRadio } from "@/composables/useFindRadio";
import type { Connection } from "@/lib/hub";
import type { RadioSearchMessage } from "@/protocol/protocol";
import { configValues, toastOf } from "@/test/fixtures";

const step = (extra: Partial<RadioSearchMessage>): RadioSearchMessage => ({ type: "radio_search", state: "trying", port: "/dev/ttyUSB0", baud: 9600, profile: "", number: 1, total: 14, ...extra });
const found = (extra: Partial<RadioSearchMessage> = {}): RadioSearchMessage => step({ state: "found", profile: "kenwood-tnc2", number: 0, total: 0, ...extra });

function setUp(saved: Record<string, string> = {}) {
  const message = shallowRef<RadioSearchMessage | null>(null);
  const error = shallowRef<Toast | null>(null);
  const connection = shallowRef<Connection>("open");
  const send = vi.fn(() => true);
  const change = vi.fn();
  const dismissUndo = vi.fn();
  const say = vi.fn();
  const values = { "tnc/profile": "kiss", "serial/port": "", "serial/baud": "9600", ...saved };
  const config = shallowRef(configValues());
  const scope = effectScope();
  const find = scope.run(() => useFindRadio(message, error, connection, send, { change, dismissUndo, expected: (key: string) => values[key as keyof typeof values] ?? "" }, config, say));
  if (!find) throw new Error("no scope");
  return { find, message, error, connection, send, change, dismissUndo, say };
}

describe("foundSettings", () => {
  it("is the profile, the port and, for a port that has a speed, the speed", () => {
    expect(foundSettings(found({ baud: 57600 }))).toEqual({ "tnc/profile": "kenwood-tnc2", "serial/port": "/dev/ttyUSB0", "serial/baud": "57600" });
    expect(foundSettings(found({ baud: null, port: "bt://AA:BB:CC:DD:EE:FF", profile: "kiss" }))).toEqual({ "tnc/profile": "kiss", "serial/port": "bt://AA:BB:CC:DD:EE:FF" });
  });
});

describe("useFindRadio", () => {
  it("asks the daemon, puts the Undo toast away for its own, and says what it asked", () => {
    const { find, send, dismissUndo } = setUp();
    find.start();
    expect(send).toHaveBeenCalledWith({ cmd: "find_radio" });
    expect(dismissUndo).toHaveBeenCalled();
    expect(find.running.value).toBe(true);
    expect(find.text.value).toBe("Looking for the radio…");
    find.start();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("says each try in the toast, with the speed or without it", async () => {
    const { find, message } = setUp();
    find.start();
    message.value = step({ number: 3 });
    await nextTick();
    expect(find.text.value).toBe("Looking for the radio: /dev/ttyUSB0 at 9600 (3 of 14)");
    message.value = step({ port: "bt://AA:BB:CC:DD:EE:FF", baud: null, number: 15, total: 15 });
    await nextTick();
    expect(find.text.value).toBe("Looking for the radio: bt://AA:BB:CC:DD:EE:FF (15 of 15)");
  });

  it("puts a radio that was found in the settings in one change, and the toast goes", async () => {
    const { find, message, change, say } = setUp();
    find.start();
    message.value = step({});
    message.value = found({ baud: 57600 });
    await nextTick();
    expect(find.running.value).toBe(false);
    expect(change).toHaveBeenCalledWith({ "tnc/profile": "kenwood-tnc2", "serial/port": "/dev/ttyUSB0", "serial/baud": "57600" });
    expect(say).not.toHaveBeenCalled();
  });

  it("changes only what differs, and says so when the settings have the radio already", async () => {
    const { find, message, change, say } = setUp({ "tnc/profile": "kenwood-tnc2" });
    find.start();
    message.value = found();
    await nextTick();
    expect(change).toHaveBeenCalledWith({ "serial/port": "/dev/ttyUSB0" });
    expect(say).not.toHaveBeenCalled();
  });

  it("says that nothing changed when the settings have the radio already", async () => {
    const { find, message, change, say } = setUp({ "tnc/profile": "kenwood-tnc2", "serial/port": "/dev/ttyUSB0", "serial/baud": "9600" });
    find.start();
    message.value = found();
    await nextTick();
    expect(change).not.toHaveBeenCalled();
    expect(say).toHaveBeenCalledWith("The radio is on /dev/ttyUSB0, as it is set");
  });

  it("sends the cancel, and the toast goes when the daemon says it is cancelled", async () => {
    const { find, message, send, say, change } = setUp();
    find.cancel();
    expect(send).not.toHaveBeenCalled();
    find.start();
    find.cancel();
    expect(send).toHaveBeenLastCalledWith({ cmd: "find_radio_cancel" });
    expect(find.running.value).toBe(true);
    message.value = step({ state: "cancelled", port: "", baud: null, number: 0, total: 0 });
    await nextTick();
    expect(find.running.value).toBe(false);
    expect(say).toHaveBeenCalledWith("Search cancelled");
    expect(change).not.toHaveBeenCalled();
  });

  it("ends when the daemon refuses or nothing answered, and the daemon's error is the toast that follows", async () => {
    const { find, error } = setUp();
    find.start();
    error.value = toastOf("find_radio: no radio answered on the ports tried", "radio.not_found");
    await nextTick();
    expect(find.running.value).toBe(false);
    find.start();
    error.value = toastOf("set_config: station/lat: 95 is not between -90 and 90", "setting.range");
    await nextTick();
    expect(find.running.value).toBe(true);
  });

  it("does not take a message for a search it did not start, and ends with the socket", async () => {
    const { find, message, change, connection, send } = setUp();
    message.value = found();
    await nextTick();
    expect(change).not.toHaveBeenCalled();
    find.start();
    connection.value = "closed";
    await nextTick();
    expect(find.running.value).toBe(false);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("does not start while the socket would refuse it", () => {
    const { find, send } = setUp();
    send.mockReturnValueOnce(false);
    find.start();
    expect(find.running.value).toBe(false);
  });
});
