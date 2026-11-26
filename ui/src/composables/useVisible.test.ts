import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";
import { pageVisible, useVisible } from "@/composables/useVisible";

function show(state: "visible" | "hidden"): void {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
  document.dispatchEvent(new Event("visibilitychange"));
}

afterEach(() => Reflect.deleteProperty(document, "visibilityState"));

function host() {
  let visible: ReturnType<typeof useVisible> | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        visible = useVisible();
        return () => h("div");
      },
    }),
  );
  return { wrapper, visible: () => visible?.value };
}

describe("pageVisible", () => {
  it("is one value for every caller, kept by one listener", () => {
    const first = pageVisible();
    const second = pageVisible();
    expect(second).toBe(first);
    show("hidden");
    expect(first.value).toBe(false);
    show("visible");
    expect(second.value).toBe(true);
  });
});

describe("useVisible", () => {
  it("follows document.visibilityState", () => {
    const { visible } = host();
    expect(visible()).toBe(true);
    show("hidden");
    expect(visible()).toBe(false);
    show("visible");
    expect(visible()).toBe(true);
  });

  it("starts hidden when the page is opened in a background tab, and stops listening when unmounted", () => {
    show("hidden");
    const { wrapper, visible } = host();
    expect(visible()).toBe(false);
    wrapper.unmount();
    show("visible");
    expect(visible()).toBe(false);
  });
});
