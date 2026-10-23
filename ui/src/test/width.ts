// For the tests of what depends on how wide an element is (composables/useElementWidth.ts): the width every element reports, and a ResizeObserver that tells the elements being observed when the test changes it.
import { vi } from "vitest";

interface Watcher {
  callback: ResizeObserverCallback;
  disconnected: boolean;
}

/** Makes every element `width` px wide; the returned `set` changes it and tells the observers, `restore` puts the browser's own back. */
export function stubWidth(width: number) {
  let current = width;
  const watchers = new Set<Watcher>();
  class FakeObserver {
    private readonly watcher: Watcher;
    constructor(callback: ResizeObserverCallback) {
      this.watcher = { callback, disconnected: false };
      watchers.add(this.watcher);
    }
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {
      this.watcher.disconnected = true;
      watchers.delete(this.watcher);
    }
  }
  vi.stubGlobal("ResizeObserver", FakeObserver);
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => current });
  return {
    set(next: number): void {
      current = next;
      for (const watcher of watchers) watcher.callback([{ contentRect: { width: next } } as ResizeObserverEntry], {} as ResizeObserver);
    },
    observing: (): number => watchers.size,
    restore(): void {
      vi.unstubAllGlobals();
      Reflect.deleteProperty(HTMLElement.prototype, "clientWidth");
    },
  };
}
