import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ToastBar from "@/components/ToastBar.vue";
import type { Toast } from "@/composables/useDaemon";
import type { Notice } from "@/composables/useNotice";

const failure = (n: number, text: string, extra: Partial<Toast> = {}): Toast => ({ cmd: "send_message", text, n, ...extra }) as Toast;
const notice = (n: number, text: string): Notice => ({ text, n });

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("ToastBar", () => {
  it("shows nothing until there is a toast or a notice", () => {
    const wrapper = mount(ToastBar, { props: { toast: null } });
    expect(wrapper.find(".toast").exists()).toBe(false);
  });

  it("shows the error the daemon told, as an alert, in the line the daemon writes it", async () => {
    const wrapper = mount(ToastBar, { props: { toast: null } });
    await wrapper.setProps({ toast: failure(1, "the radio is silent") });
    const bar = wrapper.find(".toast");
    expect(bar.attributes("role")).toBe("alert");
    expect(bar.classes()).not.toContain("notice");
    expect(bar.text()).toContain("the radio is silent");
  });

  it("shows a notice as a status in the colours of the Undo toast", async () => {
    const wrapper = mount(ToastBar, { props: { toast: null, notice: null } });
    await wrapper.setProps({ notice: notice(1, "Asked OH2XYZ for its status") });
    const bar = wrapper.find(".toast");
    expect(bar.attributes("role")).toBe("status");
    expect(bar.classes()).toContain("notice");
    expect(bar.text()).toContain("Asked OH2XYZ for its status");
  });

  it("is gone after eight seconds, or after the seconds it is given", async () => {
    const wrapper = mount(ToastBar, { props: { toast: null, notice: null } });
    await wrapper.setProps({ notice: notice(1, "Copied OH2XYZ") });
    await vi.advanceTimersByTimeAsync(7999);
    expect(wrapper.find(".toast").exists()).toBe(true);
    await vi.advanceTimersByTimeAsync(2);
    expect(wrapper.find(".toast").exists()).toBe(false);
    const quick = mount(ToastBar, { props: { toast: null, seconds: 2 } });
    await quick.setProps({ toast: failure(1, "no") });
    await vi.advanceTimersByTimeAsync(2001);
    expect(quick.find(".toast").exists()).toBe(false);
  });

  it("is replaced by the next one, which has the whole time again, and a notice replaces an error and the other way", async () => {
    const wrapper = mount(ToastBar, { props: { toast: null, notice: null } });
    await wrapper.setProps({ toast: failure(1, "first") });
    await vi.advanceTimersByTimeAsync(6000);
    await wrapper.setProps({ toast: failure(2, "second") });
    await vi.advanceTimersByTimeAsync(6000);
    expect(wrapper.find(".toast").text()).toContain("second");
    await wrapper.setProps({ notice: notice(1, "Copied OH2XYZ") });
    expect(wrapper.find(".toast").classes()).toContain("notice");
    await wrapper.setProps({ toast: failure(3, "third") });
    expect(wrapper.find(".toast").attributes("role")).toBe("alert");
    await wrapper.setProps({ notice: notice(2, "Copied OH2ABC") });
    expect(wrapper.find(".toast").text()).toContain("Copied OH2ABC");
  });

  it("is closed by its button, an error or a notice", async () => {
    const wrapper = mount(ToastBar, { props: { toast: null, notice: null } });
    await wrapper.setProps({ toast: failure(1, "first") });
    await wrapper.find("button").trigger("click");
    expect(wrapper.find(".toast").exists()).toBe(false);
    await wrapper.setProps({ notice: notice(1, "Copied OH2XYZ") });
    expect(wrapper.find("button").attributes("aria-label")).toBe("Dismiss");
    await wrapper.find("button").trigger("click");
    expect(wrapper.find(".toast").exists()).toBe(false);
  });

  it("clears an empty value (the notice that the page took away) and leaves no timer behind when it goes", async () => {
    const wrapper = mount(ToastBar, { props: { toast: null, notice: null } });
    await wrapper.setProps({ notice: notice(1, "Copied OH2XYZ") });
    await wrapper.setProps({ notice: null });
    expect(wrapper.find(".toast").exists()).toBe(false);
    await wrapper.setProps({ toast: failure(1, "first") });
    wrapper.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
