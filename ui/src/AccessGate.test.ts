import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import AccessGate from "@/AccessGate.vue";
import { FakeFetch } from "@/test/fakefetch";

afterEach(() => vi.unstubAllGlobals());

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
});
