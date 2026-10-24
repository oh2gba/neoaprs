import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";
import { useToNewest } from "@/composables/useToNewest";

// happy-dom does no layout: the sizes of the scrolling box are set by hand, and ResizeObserver is a fake whose callback the test calls
let resized: (() => void) | null = null;

class FakeResizeObserver {
  constructor(callback: () => void) {
    resized = callback;
  }
  observe(): void {}
  disconnect(): void {}
}

function sized(box: HTMLElement, scrollHeight: number, clientHeight = 100): void {
  Object.defineProperty(box, "scrollHeight", { configurable: true, value: scrollHeight });
  Object.defineProperty(box, "clientHeight", { configurable: true, value: clientHeight });
}

function harness() {
  const source = ref(0);
  const Box = defineComponent({
    setup() {
      const el = ref<HTMLElement | null>(null);
      useToNewest(el, () => source.value);
      return () => h("div", { ref: el, class: "box" }, [h("ul", [h("li", "a")])]);
    },
  });
  const wrapper = mount(Box, { attachTo: document.body });
  const box = wrapper.find(".box").element as HTMLElement;
  return { wrapper, box, source };
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("requestAnimationFrame", (fn: () => void) => {
    fn();
    return 0;
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  resized = null;
});

describe("useToNewest", () => {
  it("scrolls to the end when shown and when the source changes", async () => {
    const { box, source, wrapper } = harness();
    sized(box, 500);
    source.value++;
    await nextTick();
    await nextTick();
    expect(box.scrollTop).toBe(500);
    wrapper.unmount();
  });

  it("stays at the end when the list grows later, as a hidden tab shown or a late chain does", async () => {
    const { box, wrapper } = harness();
    await nextTick();
    sized(box, 900);
    resized?.();
    expect(box.scrollTop).toBe(900);
    wrapper.unmount();
  });

  it("leaves a person who scrolled up to read where they are, until the next change of the source", async () => {
    const { box, source, wrapper } = harness();
    sized(box, 900);
    resized?.();
    box.scrollTop = 200;
    box.dispatchEvent(new Event("scroll"));
    sized(box, 1200);
    resized?.();
    expect(box.scrollTop).toBe(200);
    source.value++;
    await nextTick();
    await nextTick();
    expect(box.scrollTop).toBe(1200);
    wrapper.unmount();
  });
});
