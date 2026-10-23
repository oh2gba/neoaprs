import { describe, expect, it, vi } from "vitest";
import { canHaveWorker, registerWorker, type WorkerHost } from "@/lib/worker";

function host(over: Partial<WorkerHost> & { register?: () => Promise<unknown> } = {}): WorkerHost & { register: ReturnType<typeof vi.fn>; load: () => void } {
  const register = vi.fn(over.register ?? (() => Promise.resolve({})));
  let onLoad: () => void = () => undefined;
  return {
    navigator: "navigator" in over ? over.navigator! : { serviceWorker: { register } },
    isSecureContext: over.isSecureContext ?? true,
    document: over.document ?? { readyState: "complete" },
    addEventListener: (_type, listener) => (onLoad = listener),
    register,
    load: () => onLoad(),
  };
}

describe("registerWorker", () => {
  it("registers sw.js, relative to the page, where the page is a secure context", () => {
    const h = host();
    expect(canHaveWorker(h)).toBe(true);
    expect(registerWorker(h)).toBe(true);
    expect(h.register).toHaveBeenCalledWith("./sw.js");
  });

  it("waits for the load of the page", () => {
    const h = host({ document: { readyState: "loading" } });
    expect(registerWorker(h)).toBe(true);
    expect(h.register).not.toHaveBeenCalled();
    h.load();
    expect(h.register).toHaveBeenCalledWith("./sw.js");
  });

  it("does nothing, and says nothing, over plain http from another computer", () => {
    const h = host({ isSecureContext: false });
    expect(registerWorker(h)).toBe(false);
    expect(h.register).not.toHaveBeenCalled();
  });

  it("does nothing in a browser that has no workers", () => {
    const h = host({ navigator: {} });
    expect(registerWorker(h)).toBe(false);
  });

  it("is silent when the browser refuses", async () => {
    const h = host({ register: () => Promise.reject(new Error("refused")) });
    expect(registerWorker(h)).toBe(true);
    await Promise.resolve();
    await Promise.resolve();
    expect(h.register).toHaveBeenCalledOnce();
  });
});
