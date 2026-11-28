// The Web group of the settings form: the switch for network access, the access key and the code a
// phone opens the page from.
import { flushPromises, mount } from "@vue/test-utils";
import { shown } from "@/test/shown";
import { afterEach, describe, expect, it, vi } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { openedAt, resetSeen } from "@/test/fakealert";
import { FakeFetch } from "@/test/fakefetch";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues } from "@/test/fixtures";
import { qrMatrix, qrPath } from "@/lib/qr";
import { shallowRef } from "vue";
import type { InstallInfo } from "@/protocol/protocol";

const ON = { "web/network": "true", "web/key": "k7m2-x9pq-4hrt" };

function make(extra: Record<string, string> = {}, urls: string[] = [], kind: InstallInfo["kind"] = "deb") {
  const config = configValues(extra);
  config.urls = urls;
  const daemon = fakeDaemon({ config, install: shallowRef({ kind, appimage: "", service: false, arch: "" }) });
  return { wrapper: mount(SettingsForm, { global: withDaemon(daemon) }), send: daemon.send, say: daemon.say };
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetSeen();
});

/** The row of the phone code. */
const codeRow = (wrapper: ReturnType<typeof make>["wrapper"]) => wrapper.find(".field:has(#set-web-code-label)");

describe("the network access", () => {
  it("has a switch labelled Allow access from the network, off by default, and applies it at once", async () => {
    const { wrapper, send } = make();
    const switch_ = wrapper.find<HTMLInputElement>("#set-web-network");
    expect(wrapper.find("label[for='set-web-network']").text()).toBe("Allow access from the network");
    expect(switch_.attributes("type")).toBe("checkbox");
    expect(switch_.element.checked).toBe(false);
    await switch_.setValue(true);
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "web/network": "true" } });
  });

  it("has no switch in a container, where the page is always on the network, and shows the key", () => {
    const { wrapper } = make(ON, ["http://172.17.0.2:7303/"], "container");
    expect(wrapper.find("#set-web-network").exists()).toBe(false);
    expect(wrapper.find<HTMLInputElement>("#set-web-key").element.value).toBe("k7m2-x9pq-4hrt");
  });

  it("has no secure connection in a container, whose secure port is not published", () => {
    expect(make(ON, ["http://192.168.1.20:7303/"]).wrapper.find("#set-web-https").exists()).toBe(true);
    expect(make(ON, ["http://172.17.0.2:7303/"], "container").wrapper.find("#set-web-https").exists()).toBe(false);
  });

  it("shows neither the key nor the code while the network is off, or before the daemon has made a key", () => {
    expect(make().wrapper.find("#set-web-key").exists()).toBe(false);
    expect(make({ "web/network": "true" }).wrapper.find("#set-web-key").exists()).toBe(false);
    expect(make({ "web/key": "k7m2-x9pq-4hrt" }).wrapper.find("#set-web-key").exists()).toBe(false);
    expect(make({}, ["http://192.168.1.20:7303/"]).wrapper.find(".phonecode").exists()).toBe(false);
    expect(make({ "web/network": "true" }, ["http://192.168.1.20:7303/"]).wrapper.find(".phonecode").exists()).toBe(
      false,
    );
  });

  it("does not show the key of a switch that is only turned on in the form, until the daemon has made one", async () => {
    const { wrapper } = make({ "web/key": "k7m2-x9pq-4hrt" });
    await wrapper.find("#set-web-network").setValue(true);
    expect(wrapper.find("#set-web-key").exists()).toBe(false);
  });

  it("shows the access key, read-only, and under it the code a phone opens the page from, once the network is on", () => {
    const { wrapper } = make(ON, ["http://192.168.1.20:7303/", "http://raspberrypi.local:7303/"]);
    const key = wrapper.find<HTMLInputElement>("#set-web-key");
    expect(key.element.value).toBe("k7m2-x9pq-4hrt");
    expect(key.attributes("readonly")).toBeDefined();
    expect(wrapper.find("label[for='set-web-key']").text()).toBe("Access key");
    const row = codeRow(wrapper);
    expect(row.find("#set-web-code-label").text()).toBe("Open on a phone");
    const code = row.find("svg.phonecode");
    expect(code.attributes("role")).toBe("img");
    expect(code.attributes("aria-labelledby")).toBe("set-web-code-label");
    expect(key.element.closest(".field")?.nextElementSibling).toBe(row.element);
  });

  it("holds in the code the first address with the key after #, and prints neither the address, the port nor the key", () => {
    const { wrapper } = make(ON, ["http://192.168.1.20:7303/", "http://raspberrypi.local:7303/"]);
    const row = codeRow(wrapper);
    expect(row.find("path").attributes("d")).toBe(qrPath(qrMatrix("http://192.168.1.20:7303/#key=k7m2-x9pq-4hrt")).d);
    for (const inside of ["192.168", ".local", ":7303", "k7m2", "x9pq", "4hrt", "#key"])
      expect(row.html()).not.toContain(inside);
    expect(row.findAll("input")).toHaveLength(0);
  });

  it("has no code while the daemon has no address for other devices", () => {
    const { wrapper } = make(ON, []);
    expect(wrapper.find("#set-web-key").exists()).toBe(true);
    expect(wrapper.find(".phonecode").exists()).toBe(false);
    expect(wrapper.find("#set-web-code-label").exists()).toBe(false);
  });

  it("draws the new key into the same code when the key is renewed, its box and its size in modules kept", async () => {
    const config = shallowRef(configValues(ON));
    config.value.urls = ["http://192.168.1.20:7303/"];
    const wrapper = mount(SettingsForm, { global: withDaemon(fakeDaemon({ config })) });
    const before = wrapper.find("svg.phonecode");
    const [box, d] = [before.attributes("viewBox"), before.find("path").attributes("d")];
    config.value = { ...config.value, values: { ...config.value.values, "web/key": "abcd-efgh-jkmn" } };
    await flushPromises();
    const after = wrapper.find("svg.phonecode");
    expect(after.element).toBe(before.element);
    expect(after.attributes("viewBox")).toBe(box);
    expect(after.find("path").attributes("d")).not.toBe(d);
    expect(after.find("path").attributes("d")).toBe(qrPath(qrMatrix("http://192.168.1.20:7303/#key=abcd-efgh-jkmn")).d);
  });

  it("makes a new key only on the second press, and says so in the toast when the daemon does not answer", async () => {
    const daemon = new FakeFetch(204);
    vi.stubGlobal("fetch", daemon.fetch);
    const { wrapper, say } = make(ON);
    const button = () => wrapper.findAll("button").find((b) => b.text().startsWith("New key"));
    expect(shown(button())).toBe("New key");
    expect(
      button()
        ?.findAll(".twowords > span")
        .map((face) => face.text()),
    ).toEqual(["New key", "sure?"]); // (both are there: the button keeps its width)
    await button()?.trigger("click");
    expect(shown(button())).toBe("sure?");
    expect(daemon.calls).toEqual([]);
    await button()?.trigger("click");
    await flushPromises();
    expect(daemon.calls.map((c) => [c.method, c.url])).toEqual([["POST", "http://127.0.0.1:7303/access/new"]]);
    expect(say).not.toHaveBeenCalled();
    daemon.status = 500;
    await button()?.trigger("click");
    await button()?.trigger("click");
    await flushPromises();
    expect(say).toHaveBeenCalledExactlyOnceWith("No answer from NeoAPRS.");
  });
});

describe("turning the network access off", () => {
  const off = async (wrapper: ReturnType<typeof make>["wrapper"]) => wrapper.find("#set-web-network").setValue(false);
  const buttons = (wrapper: ReturnType<typeof make>["wrapper"]) =>
    wrapper.findAll(".confirm-row button").map((b) => b.text());

  it("just happens on the computer NeoAPRS runs on (a loopback address): nothing asks", async () => {
    for (const host of ["127.0.0.1", "localhost"]) {
      openedAt(host);
      const { wrapper, send } = make(ON);
      await off(wrapper);
      expect(wrapper.find(".confirm-row").exists()).toBe(false);
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "web/network": "false" } });
    }
  });

  it("asks first on a page opened from another device, and sends nothing until Yes", async () => {
    openedAt("192.168.1.20");
    const { wrapper, send } = make(ON);
    await off(wrapper);
    expect(wrapper.find(".confirm-row").text()).toContain("This device will lose the page. Turn off?");
    expect(buttons(wrapper)).toEqual(["Yes", "Cancel"]);
    expect(send).not.toHaveBeenCalled();
    await wrapper.findAll(".confirm-row button")[0]?.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "web/network": "false" } });
    expect(wrapper.find(".confirm-row").exists()).toBe(false);
  });

  it("leaves the switch on and sends nothing on Cancel, or on Esc", async () => {
    openedAt("raspberrypi.local");
    const { wrapper, send } = make(ON);
    await off(wrapper);
    await wrapper.findAll(".confirm-row button")[1]?.trigger("click");
    expect(wrapper.find<HTMLInputElement>("#set-web-network").element.checked).toBe(true);
    expect(wrapper.find(".confirm-row").exists()).toBe(false);
    await off(wrapper);
    await wrapper.find(".confirm-row").trigger("keydown", { key: "Escape" });
    expect(wrapper.find<HTMLInputElement>("#set-web-network").element.checked).toBe(true);
    expect(send).not.toHaveBeenCalled();
  });

  it("does not ask when the network is turned on, or for any other setting", async () => {
    openedAt("192.168.1.20");
    const { wrapper, send } = make();
    await wrapper.find("#set-web-network").setValue(true);
    await wrapper.find("#set-radio-1-digipeat").setValue(true);
    expect(wrapper.find(".confirm-row").exists()).toBe(false);
    // the next waits for its answer
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "web/network": "true" } });
  });

  it("asks before the secure connection (https) is switched on or off on a page opened from another device, and not on this computer", async () => {
    openedAt("192.168.1.20");
    const remote = make(ON);
    await remote.wrapper.find("#set-web-https").setValue(true);
    expect(remote.wrapper.find(".confirm-row").text()).toContain("This device will lose the page. Turn on?");
    expect(remote.send).not.toHaveBeenCalled();
    await remote.wrapper.findAll(".confirm-row button")[0]?.trigger("click");
    expect(remote.send).toHaveBeenCalledWith({ cmd: "set_config", values: { "web/https": "true" } });
    openedAt("127.0.0.1");
    const local = make(ON);
    await local.wrapper.find("#set-web-https").setValue(true);
    expect(local.wrapper.find(".confirm-row").exists()).toBe(false);
    expect(local.send).toHaveBeenCalledWith({ cmd: "set_config", values: { "web/https": "true" } });
  });
});
