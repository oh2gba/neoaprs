import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";
import { useVisible } from "@/composables/useVisible";

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
