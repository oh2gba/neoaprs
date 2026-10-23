import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import Disclosure from "@/components/Disclosure.vue";

const opened = (wrapper: ReturnType<typeof mount>) => wrapper.find<HTMLDetailsElement>("details").element.open;

describe("Disclosure", () => {
  it("is closed, with its title, unless it is told to be open", () => {
    const closed = mount(Disclosure, { props: { title: "Details" }, slots: { default: "<p>inside</p>" } });
    expect(closed.find("summary").text()).toBe("Details");
    expect(opened(closed)).toBe(false);
    expect(opened(mount(Disclosure, { props: { title: "Route", open: true } }))).toBe(true);
  });

  it("opens when it is told to later, and is never closed by the page", async () => {
    const wrapper = mount(Disclosure, { props: { title: "Route" } });
    await wrapper.setProps({ open: true });
    expect(opened(wrapper)).toBe(true);
    await wrapper.setProps({ open: false });
    expect(opened(wrapper)).toBe(true);
  });

  it("keeps what the person did with it", async () => {
    const wrapper = mount(Disclosure, { props: { title: "Route", open: true } });
    wrapper.find<HTMLDetailsElement>("details").element.open = false;
    await wrapper.find("details").trigger("toggle");
    await wrapper.setProps({ title: "Route again" });
    expect(opened(wrapper)).toBe(false);
  });
});
