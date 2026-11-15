import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import AccessGate from "@/AccessGate.vue";
import { FakeFetch } from "@/test/fakefetch";

afterEach(() => {
  vi.unstubAllGlobals();
  history.replaceState(null, "", "/");
});

function open(status: number) {
  const daemon = new FakeFetch(status);
  vi.stubGlobal("fetch", daemon.fetch);
  return { wrapper: mount(AccessGate, { global: { stubs: { App: { template: "<p class='page'>the page</p>" } } } }), daemon };
}

describe("AccessGate", () => {
  it("shows nothing while it asks, then the page for a device that is let in", async () => {
    const { wrapper } = open(204);
    expect(wrapper.find(".page").exists()).toBe(false);
    expect(wrapper.find(".keyscreen").exists()).toBe(false);
    await flushPromises();
    expect(wrapper.find(".page").exists()).toBe(true);
    expect(wrapper.find(".keyscreen").exists()).toBe(false);
  });

  it("shows the key screen, and not the page, to a device that is not, until the right key is typed", async () => {
    const { wrapper, daemon } = open(401);
    await flushPromises();
    expect(wrapper.find(".keyscreen").exists()).toBe(true);
    expect(wrapper.find(".page").exists()).toBe(false);
    daemon.status = 204;
    await wrapper.find("input").setValue("k7m2-x9pq-4hrt");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(wrapper.find(".keyscreen").exists()).toBe(false);
    expect(wrapper.find(".page").exists()).toBe(true);
  });

  describe("a phone that came by the code, with the key in the address", () => {
    /** The daemon answers each request in turn with the next status, and the address's fragment at each request is kept. */
    function scanned(address: string, ...statuses: number[]) {
      history.replaceState(null, "", address);
      const daemon = new FakeFetch();
      const fragments: string[] = [];
      vi.stubGlobal("fetch", ((input, init) => {
        fragments.push(location.hash);
        daemon.status = statuses.shift() ?? 0;
        return daemon.fetch(input, init);
      }) satisfies typeof fetch);
      const wrapper = mount(AccessGate, { global: { stubs: { App: { template: "<p class='page'>the page</p>" } } } });
      return { wrapper, daemon, fragments };
    }
    const posted = (daemon: FakeFetch) => daemon.calls.filter((c) => c.method === "POST").map((c) => JSON.parse(c.body) as unknown);

    it("takes the key out of the address and the history before it asks anything, and opens the page with no key screen when the daemon takes it", async () => {
      const before = history.length;
      const { wrapper, daemon, fragments } = scanned("/?lang=fi#key=k7m2-x9pq-4hrt", 401, 204);
      await flushPromises();
      expect(fragments).toEqual(["", ""]);
      expect(location.href).toBe("http://127.0.0.1:7303/?lang=fi");
      expect(history.length).toBe(before);
      expect(posted(daemon)).toEqual([{ key: "k7m2-x9pq-4hrt" }]);
      expect(wrapper.find(".page").exists()).toBe(true);
      expect(wrapper.find(".keyscreen").exists()).toBe(false);
    });

    it.each([
      [403, "a wrong key"],
      [429, "an address shut out"],
      [0, "no answer"],
    ])("shows the key screen as it always is, empty and with no error line, for %s (%s)", async (status) => {
      const { wrapper, daemon } = scanned("/#key=k7m2-x9pq-4hrt", 401, status);
      await flushPromises();
      expect(posted(daemon)).toHaveLength(1);
      expect(wrapper.find(".keyscreen").exists()).toBe(true);
      expect(wrapper.find<HTMLInputElement>("#access-key").element.value).toBe("");
      expect(wrapper.find(".field-error").exists()).toBe(false);
      expect(wrapper.find(".page").exists()).toBe(false);
      expect(location.hash).toBe("");
    });

    it("opens a page that is let in already with the key taken out of the address, and sends no key", async () => {
      const { wrapper, daemon } = scanned("/#key=k7m2-x9pq-4hrt", 204);
      await flushPromises();
      expect(daemon.calls.map((c) => c.method)).toEqual(["GET"]);
      expect(location.hash).toBe("");
      expect(wrapper.find(".page").exists()).toBe(true);
    });

    it("leaves the app window's #app in the address, and sends no key", async () => {
      const { wrapper, daemon } = scanned("/#app", 401);
      await flushPromises();
      expect(location.hash).toBe("#app");
      expect(posted(daemon)).toEqual([]);
      expect(wrapper.find(".keyscreen").exists()).toBe(true);
    });

    it("sends at most the 64 characters the daemon reads of a key, so a long one is a wrong key and not a refused request", async () => {
      const { daemon } = scanned(`/#key=${"k".repeat(200)}`, 401, 403);
      await flushPromises();
      expect(posted(daemon)).toEqual([{ key: "k".repeat(64) }]);
    });
  });
});
