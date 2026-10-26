import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { useDark } from "@/composables/useDark";

/** The viewer's colour scheme as a media query that the test changes: what `window.matchMedia` gives for `(prefers-color-scheme: dark)`. */
class FakeScheme {
  listeners = new Set<(event: MediaQueryListEvent) => void>();
  constructor(public matches: boolean) {}
  addEventListener(type: string, listener: (event: MediaQueryListEvent) => void): void {
    if (type === "change") this.listeners.add(listener);
  }
  removeEventListener(type: string, listener: (event: MediaQueryListEvent) => void): void {
    if (type === "change") this.listeners.delete(listener);
  }
  switchTo(dark: boolean): void {
    this.matches = dark;
    for (const listener of this.listeners) listener({ matches: dark } as MediaQueryListEvent);
  }
}

function pageWith(scheme: FakeScheme | null) {
  const asked: string[] = [];
  window.matchMedia = scheme
    ? (query: string) => {
        asked.push(query);
        return scheme as unknown as MediaQueryList;
      }
    : (undefined as unknown as typeof window.matchMedia);
  let dark: { value: boolean } | undefined;
  const wrapper = mount(
    defineComponent({
      setup() {
        dark = useDark();
        return () => h("p", dark?.value ? "dark" : "light");
      },
    }),
  );
  return { wrapper, asked, dark: () => dark as { value: boolean } };
}

const original = window.matchMedia;
afterEach(() => {
  window.matchMedia = original;
});

describe("useDark", () => {
  it("asks for the dark colour scheme and starts as the system is", () => {
    const light = pageWith(new FakeScheme(false));
    expect(light.asked).toEqual(["(prefers-color-scheme: dark)"]);
    expect(light.dark().value).toBe(false);
    expect(pageWith(new FakeScheme(true)).dark().value).toBe(true);
  });

  it("follows the system when the viewer changes the scheme, both ways", async () => {
    const scheme = new FakeScheme(false);
    const { wrapper, dark } = pageWith(scheme);
    scheme.switchTo(true);
    await nextTick();
    expect(dark().value).toBe(true);
    expect(wrapper.text()).toBe("dark");
    scheme.switchTo(false);
    await nextTick();
    expect(dark().value).toBe(false);
    expect(wrapper.text()).toBe("light");
  });

  it("stops listening when the component is gone", () => {
    const scheme = new FakeScheme(false);
    const { wrapper } = pageWith(scheme);
    expect(scheme.listeners.size).toBe(1);
    wrapper.unmount();
    expect(scheme.listeners.size).toBe(0);
  });

  it("is light where the browser cannot say (no media queries) and listens to nothing", () => {
    const { dark, wrapper } = pageWith(null);
    expect(dark().value).toBe(false);
    wrapper.unmount();
  });
});
