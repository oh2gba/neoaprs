import { describe, expect, it, vi } from "vitest";
import { effectScope, nextTick, shallowRef } from "vue";
import type { Toast } from "@/composables/useDaemon";
import { useFindRadio } from "@/composables/useFindRadio";
import type { Connection } from "@/lib/hub";
import type { RadioSearchMessage } from "@/protocol/protocol";
import { configValues, radioSearch, toastOf } from "@/test/fixtures";

const step = (extra: Partial<RadioSearchMessage>): RadioSearchMessage => radioSearch(extra);
const found = (extra: Partial<RadioSearchMessage> = {}): RadioSearchMessage => step({ state: "found", profile: "kenwood-tnc2", number: 0, total: 0, ...extra });

function setUp(saved: Record<string, string> = {}) {
  const message = shallowRef<RadioSearchMessage | null>(null);
  const error = shallowRef<Toast | null>(null);
  const connection = shallowRef<Connection>("open");
  const send = vi.fn(() => true);
  const change = vi.fn();
  const say = vi.fn();
  const values: Record<string, string> = { "radio/1/port": "", "radio/1/baud": "9600", ...saved };
  const config = shallowRef(configValues());
  const scope = effectScope();
  const find = scope.run(() => useFindRadio(message, error, connection, send, { change, expected: (key: string) => values[key] ?? "" }, config, say));
  if (!find) throw new Error("no scope");
  return { find, message, error, connection, send, change, say };
}

describe("useFindRadio", () => {
  it("asks the daemon and says what it asked", () => {
    const { find, send } = setUp();
    find.start();
    expect(send).toHaveBeenCalledWith({ cmd: "find_radio" });
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
    expect(change).toHaveBeenCalledWith({ "radio/1/port": "/dev/ttyUSB0", "radio/1/baud": "57600" });
    expect(say).not.toHaveBeenCalled();
  });

  it("changes only what differs, and says so when the settings have the radio already", async () => {
    const { find, message, change, say } = setUp();
    find.start();
    message.value = found();
    await nextTick();
    expect(change).toHaveBeenCalledWith({ "radio/1/port": "/dev/ttyUSB0" });
    expect(say).not.toHaveBeenCalled();
  });

  it("says that nothing changed when the settings have the radio already", async () => {
    const { find, message, change, say } = setUp({ "radio/1/port": "/dev/ttyUSB0", "radio/1/baud": "9600" });
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

// The search for a radio other than radio 1: the one whose box the button is in.
describe("useFindRadio for one radio of several", () => {
  it("asks the daemon for that radio, names it in the toast, and cancels that search", async () => {
    const { find, send, message } = setUp();
    find.start(3);
    expect(send).toHaveBeenLastCalledWith({ cmd: "find_radio", radio: 3 });
    expect(find.text.value).toBe("Looking for the radio…");
    find.cancel();
    expect(send).toHaveBeenLastCalledWith({ cmd: "find_radio_cancel", radio: 3 });
    message.value = step({ state: "cancelled", port: "", baud: null, number: 0, total: 0, radio: 3 });
    await nextTick();
    expect(find.running.value).toBe(false);
  });

  it("takes the radio of the box a press came from, with its name where the box gives one, radio 1 by its id too", () => {
    const { find, send } = setUp();
    const box = document.createElement("fieldset");
    box.dataset["radio"] = "4";
    box.dataset["radioName"] = "20 m";
    box.dataset["radioType"] = "kiss";
    const button = box.appendChild(document.createElement("button"));
    button.addEventListener("click", (event) => find.start(event));
    button.click();
    expect(send).toHaveBeenLastCalledWith({ cmd: "find_radio", radio: 4 });
    expect(find.text.value).toBe("20 m: Looking for the radio…");
    const other = setUp();
    const one = document.createElement("fieldset");
    one.dataset["radio"] = "1";
    const press = one.appendChild(document.createElement("button"));
    press.addEventListener("click", (event) => other.find.start(event));
    press.click();
    expect(other.send).toHaveBeenLastCalledWith({ cmd: "find_radio", radio: 1 });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("puts what it finds into that radio's own settings, and its type by radio_change when the TNC found is of another", async () => {
    const { find, send, change, message } = setUp();
    const box = document.createElement("fieldset");
    box.dataset["radio"] = "3";
    box.dataset["radioType"] = "kiss";
    const button = box.appendChild(document.createElement("button"));
    button.addEventListener("click", (event) => find.start(event));
    button.click();
    message.value = found({ baud: 9600, radio: 3, radio_type: "kenwood-tnc2" });
    await nextTick();
    expect(send).toHaveBeenLastCalledWith({ cmd: "radio_change", radio: 3, type: "kenwood-tnc2" });
    expect(change).toHaveBeenCalledWith({ "radio/3/port": "/dev/ttyUSB0", "radio/3/baud": "9600" });
    expect(change.mock.calls.flatMap((call: unknown[]) => Object.keys(call[0] as Record<string, string>))).not.toContain("radio/3/type");
  });
});
