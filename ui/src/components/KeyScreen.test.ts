import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import KeyScreen from "@/components/KeyScreen.vue";
import { FakeFetch } from "@/test/fakefetch";

afterEach(() => vi.unstubAllGlobals());

function make(status: number) {
  const daemon = new FakeFetch(status);
  vi.stubGlobal("fetch", daemon.fetch);
  return { wrapper: mount(KeyScreen, { attachTo: document.body }), daemon };
}

describe("KeyScreen", () => {
  it("is one field and one button and nothing more", () => {
    const { wrapper } = make(204);
    expect(wrapper.findAll("input")).toHaveLength(1);
    expect(wrapper.findAll("button")).toHaveLength(1);
    expect(wrapper.text()).toBe("Open");
    expect(wrapper.find("input").attributes("placeholder")).toBe("xxxx-xxxx-xxxx");
    expect(wrapper.find("input").element).toBe(document.activeElement);
    wrapper.unmount();
  });

  it("has the button off until something is typed", async () => {
    const { wrapper } = make(204);
    expect(wrapper.find("button").attributes("disabled")).toBeDefined();
    await wrapper.find("input").setValue("k7m2");
    expect(wrapper.find("button").attributes("disabled")).toBeUndefined();
    wrapper.unmount();
  });

  it("sends the key and says the page may open when it is the right one", async () => {
    const { wrapper, daemon } = make(204);
    await wrapper.find("input").setValue("k7m2-x9pq-4hrt");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(JSON.parse(daemon.calls[0]?.body ?? "")).toEqual({ key: "k7m2-x9pq-4hrt" });
    expect(wrapper.emitted("opened")).toHaveLength(1);
    wrapper.unmount();
  });

  it("says a wrong key under the field, keeps the page shut, and forgets the complaint when the key is edited", async () => {
    const { wrapper } = make(403);
    await wrapper.find("input").setValue("aaaa-aaaa-aaaa");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(wrapper.find("[role=alert]").text()).toBe("Wrong key.");
    expect(wrapper.emitted("opened")).toBeUndefined();
    await wrapper.find("input").setValue("aaaa-aaaa-aaab");
    expect(wrapper.find("[role=alert]").exists()).toBe(false);
    wrapper.unmount();
  });

  it("says when the address is shut out", async () => {
    const { wrapper } = make(429);
    await wrapper.find("input").setValue("aaaa-aaaa-aaaa");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(wrapper.find("[role=alert]").text()).toBe("Too many tries. Wait a few minutes.");
    wrapper.unmount();
  });
});
