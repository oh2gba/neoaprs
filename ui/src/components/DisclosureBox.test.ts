import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import DisclosureBox from "@/components/DisclosureBox.vue";

const opened = (wrapper: ReturnType<typeof mount>) => wrapper.find<HTMLDetailsElement>("details").element.open;

describe("DisclosureBox", () => {
  it("is closed, with its title, unless it is told to be open", () => {
    const closed = mount(DisclosureBox, { props: { title: "Details" }, slots: { default: "<p>inside</p>" } });
    expect(closed.find("summary").text()).toBe("Details");
    expect(opened(closed)).toBe(false);
    expect(opened(mount(DisclosureBox, { props: { title: "Route", open: true } }))).toBe(true);
  });

  it("opens when it is told to later, and is never closed by the page", async () => {
    const wrapper = mount(DisclosureBox, { props: { title: "Route" } });
    await wrapper.setProps({ open: true });
    expect(opened(wrapper)).toBe(true);
    await wrapper.setProps({ open: false });
    expect(opened(wrapper)).toBe(true);
  });

  it("has the look of the page's heading that opens, unless it is plain: then the class of the caller is the look, and what is under the heading is not wrapped", () => {
    const styled = mount(DisclosureBox, { props: { title: "Details" }, slots: { default: "<p>inside</p>" } });
    expect(styled.find("details").classes()).toEqual(["disclosure"]);
    expect(styled.find(".disclosure-body p").exists()).toBe(true);
    const plain = mount(DisclosureBox, {
      props: { title: "Raw", plain: true, summaryClass: { problem: true } },
      attrs: { class: "more" },
      slots: { default: "<pre>inside</pre>" },
    });
    expect(plain.find("details").classes()).toEqual(["more"]);
    expect(plain.find("summary").classes()).toEqual(["problem"]);
    expect(plain.find(".disclosure-body").exists()).toBe(false);
    expect(plain.find("details > pre").exists()).toBe(true);
  });

  it("keeps what the person did with it", async () => {
    const wrapper = mount(DisclosureBox, { props: { title: "Route", open: true } });
    wrapper.find<HTMLDetailsElement>("details").element.open = false;
    await wrapper.find("details").trigger("toggle");
    await wrapper.setProps({ title: "Route again" });
    expect(opened(wrapper)).toBe(false);
  });
});
