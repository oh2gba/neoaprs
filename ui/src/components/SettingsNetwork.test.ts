// The Web group of the settings form: the switch for network access, the access key and the addresses.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { FakeFetch } from "@/test/fakefetch";
import { configValues } from "@/test/fixtures";

const ON = { "web/network": "true", "web/key": "k7m2-x9pq-4hrt" };

function make(extra: Record<string, string> = {}, urls: string[] = []) {
  const config = configValues(extra);
  config.urls = urls;
  const send = vi.fn(() => true);
  return { wrapper: mount(SettingsForm, { props: { config, lastError: null, send } }), send };
}

afterEach(() => vi.unstubAllGlobals());

describe("the network access", () => {
  it("has a switch labelled Allow access from the network, off by default, and sends it like any setting", async () => {
    const { wrapper, send } = make();
    const switch_ = wrapper.find<HTMLInputElement>("#set-web-network");
    expect(wrapper.find("label[for='set-web-network']").text()).toBe("Allow access from the network");
    expect(switch_.attributes("type")).toBe("checkbox");
    expect(switch_.element.checked).toBe(false);
    await switch_.setValue(true);
    await wrapper.find("form").trigger("submit");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "web/network": "true" } });
  });

  it("shows neither the key nor the addresses while the network is off, or before the daemon has made a key", () => {
    expect(make().wrapper.find("#set-web-key").exists()).toBe(false);
    expect(make({ "web/network": "true" }).wrapper.find("#set-web-key").exists()).toBe(false);
    expect(make({ "web/key": "k7m2-x9pq-4hrt" }).wrapper.find("#set-web-key").exists()).toBe(false);
    expect(make({}, ["http://192.168.1.20:7303/"]).wrapper.find("#set-web-url-0").exists()).toBe(false);
  });

  it("does not show the key of a switch that is only turned on in the form, until it is saved", async () => {
    const { wrapper } = make({ "web/key": "k7m2-x9pq-4hrt" });
    await wrapper.find("#set-web-network").setValue(true);
    expect(wrapper.find("#set-web-key").exists()).toBe(false);
  });

  it("shows the access key, read-only, and the addresses to open the page at, once the network is on", () => {
    const { wrapper } = make(ON, ["http://192.168.1.20:7303/", "http://raspberrypi.local:7303/"]);
    const key = wrapper.find<HTMLInputElement>("#set-web-key");
    expect(key.element.value).toBe("k7m2-x9pq-4hrt");
    expect(key.attributes("readonly")).toBeDefined();
    expect(wrapper.find("label[for='set-web-key']").text()).toBe("Access key");
    expect(wrapper.findAll(".urls input").map((i) => (i.element as HTMLInputElement).value)).toEqual([
      "http://192.168.1.20:7303/",
      "http://raspberrypi.local:7303/",
    ]);
    expect(wrapper.find("label[for='set-web-url-0']").text()).toBe("Open at");
    expect(wrapper.find("button[type=submit]").attributes("disabled")).toBeDefined(); // (the key is shown, not edited: nothing is changed)
  });

  it("makes a new key only on the second press, and says so when the daemon does not answer", async () => {
    const daemon = new FakeFetch(204);
    vi.stubGlobal("fetch", daemon.fetch);
    const { wrapper } = make(ON);
    const button = () => wrapper.findAll("button").find((b) => b.text() === "New key" || b.text() === "sure?");
    expect(button()?.text()).toBe("New key");
    await button()?.trigger("click");
    expect(button()?.text()).toBe("sure?");
    expect(daemon.calls).toEqual([]);
    await button()?.trigger("click");
    await flushPromises();
    expect(daemon.calls.map((c) => [c.method, c.url])).toEqual([["POST", "http://127.0.0.1:7303/access/new"]]);
    expect(wrapper.find(".field-result").exists()).toBe(false);
    daemon.status = 500;
    await button()?.trigger("click");
    await button()?.trigger("click");
    await flushPromises();
    expect(wrapper.find(".field-result").text()).toBe("No answer from the daemon.");
  });
});
