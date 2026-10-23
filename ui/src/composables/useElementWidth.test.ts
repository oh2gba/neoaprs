import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, ref } from "vue";
import { useElementWidth } from "@/composables/useElementWidth";
import { stubWidth } from "@/test/width";

let width: ReturnType<typeof stubWidth> | undefined;
afterEach(() => width?.restore());

function host() {
  let seen: ReturnType<typeof useElementWidth> | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        const el = ref<HTMLElement | null>(null);
        seen = useElementWidth(el);
        return () => h("div", { ref: el });
      },
    }),
  );
  return { wrapper, width: () => seen?.value };
}

describe("useElementWidth", () => {
  it("is the width of the element once it is mounted, and follows the observer", () => {
    width = stubWidth(480);
    const { width: current } = host();
    expect(current()).toBe(480);
    width.set(720);
    expect(current()).toBe(720);
  });

  it("keeps the last width while the element has none (it is hidden)", () => {
    width = stubWidth(480);
    const { width: current } = host();
    width.set(0);
    expect(current()).toBe(480);
  });

  it("stops observing when the component goes", () => {
    width = stubWidth(480);
    const { wrapper } = host();
    expect(width.observing()).toBe(1);
    wrapper.unmount();
    expect(width.observing()).toBe(0);
  });
});
