import { describe, expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { useSettingsForm } from "@/composables/useSettingsForm";
import type { Toast } from "@/composables/useDaemon";
import type { Scope } from "@/lib/settings";
import type { ConfigValues } from "@/protocol/protocol";
import { configValues } from "@/test/fixtures";

function setUp(scope: Scope = "beacon") {
  const config = ref<ConfigValues | null>(configValues());
  const lastError = ref<Toast | null>(null);
  const send = vi.fn(() => true);
  const form = useSettingsForm(config, lastError, send, scope);
  return { config, lastError, send, form };
}

describe("useSettingsForm", () => {
  it("starts as the daemon's values, not dirty", () => {
    const { form } = setUp();
    expect(form.draft["station/call"]).toBe("OH2GBA");
    expect(form.dirty.value).toBe(false);
    expect(form.groups.value.map((g) => g.id)).toEqual(["station", "beacon", "status"]);
    expect(setUp("settings").form.groups.value.map((g) => g.id)).toEqual(["serial", "web", "log", "messages", "map", "update"]);
  });

  it("counts and sends only the keys of its scope", () => {
    const { form, send } = setUp("settings");
    form.edit("station/lat", "60.5");
    expect(form.dirty.value).toBe(false);
    form.edit("serial/baud", "4800");
    form.save();
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "serial/baud": "4800" } });
  });

  it("takes an error only for a key of its scope", async () => {
    const { form, lastError } = setUp("settings");
    form.edit("serial/baud", "5");
    form.save();
    lastError.value = { text: "set_config: station/lat: 95 is not between -90 and 90", n: 1 };
    await nextTick();
    expect(form.errors["station/lat"]).toBeUndefined();
  });

  it("sends only the keys that were changed", () => {
    const { form, send } = setUp();
    form.edit("station/lat", "60.5");
    form.edit("station/comment", "NeoAPRS"); // the same as it is
    expect(form.dirty.value).toBe(true);
    form.save();
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/lat": "60.5" } });
    expect(form.saving.value).toBe(true);
  });

  it("sends nothing when nothing changed", () => {
    const { form, send } = setUp();
    form.save();
    expect(send).not.toHaveBeenCalled();
  });

  it("is saved when the daemon tells the settings again, with the value the way it writes it", async () => {
    const { form, config } = setUp();
    form.edit("station/call", "oh2gba-9");
    form.save();
    config.value = configValues({ "station/call": "OH2GBA-9" });
    await nextTick();
    expect(form.saving.value).toBe(false);
    expect(form.saved.value).toBe(true);
    expect(form.draft["station/call"]).toBe("OH2GBA-9");
    expect(form.dirty.value).toBe(false);
  });

  it("shows the error that names a setting under that setting, and keeps what was typed", async () => {
    const { form, lastError } = setUp();
    form.edit("station/lat", "95");
    form.save();
    lastError.value = { text: "set_config: station/lat: 95 is not between -90 and 90", n: 1 };
    await nextTick();
    expect(form.errors["station/lat"]).toBe("95 is not between -90 and 90");
    expect(form.saving.value).toBe(false);
    expect(form.draft["station/lat"]).toBe("95");
    form.edit("station/lat", "60");
    expect(form.errors["station/lat"]).toBeUndefined();
  });

  it("does not take an error it did not wait for", async () => {
    const { form, lastError } = setUp();
    lastError.value = { text: "forget_station: call: is missing", n: 1 };
    await nextTick();
    expect(Object.keys(form.errors)).toEqual([]);
  });

  it("follows a value the daemon changes unless the user has changed it", async () => {
    const { form, config } = setUp();
    form.edit("station/comment", "mine");
    config.value = configValues({ "station/comment": "theirs", "serial/baud": "4800" });
    await nextTick();
    expect(form.draft["station/comment"]).toBe("mine");
    expect(form.draft["serial/baud"]).toBe("4800");
  });

  it("puts the daemon's values back on revert", () => {
    const { form } = setUp();
    form.edit("station/lat", "1");
    form.revert();
    expect(form.draft["station/lat"]).toBe("60.17");
    expect(form.dirty.value).toBe(false);
  });

  it("does not say it is saving when the command could not be sent", () => {
    const config = ref<ConfigValues | null>(configValues());
    const form = useSettingsForm(config, ref(null), () => false, "beacon");
    form.edit("station/lat", "1");
    form.save();
    expect(form.saving.value).toBe(false);
  });
});
