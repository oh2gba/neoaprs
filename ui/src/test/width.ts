// For tests that depend on an element's width (useElementWidth): the width every element reports,
// and a ResizeObserver that notifies the observed elements when it changes.
import { vi } from "vitest";

interface Watcher {
  callback: ResizeObserverCallback;
  disconnected: boolean;
}

/**
 * Make every element `width` px wide; `set` changes it and notifies the observers, `restore` undoes
 * it.
 */
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
