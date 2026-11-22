import { describe, expect, it } from "vitest";
import { daemonTells, inApp } from "@/lib/shell";

const memory = (): Storage => {
  const kept = new Map<string, string>();
  return { getItem: (k) => kept.get(k) ?? null, setItem: (k, v) => void kept.set(k, v) } as Storage;
};

const LINUX =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/6.8.0 Chrome/130.0.0.0 Safari/537.36";
const WINDOWS =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0";
const MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)";

describe("the app's window", () => {
  it("is known by the fragment, and by what the window remembered of it", () => {
    const kept = memory();
    expect(inApp("", kept)).toBe(false);
    expect(inApp("#app", kept)).toBe(true);
    expect(inApp("", kept)).toBe(true);
  });

  it("has the daemon's own alert tell on Linux and Windows, where its command makes the notification and the sound", () => {
    expect(daemonTells("#app", memory(), LINUX)).toBe(true);
    expect(daemonTells("#app", memory(), WINDOWS)).toBe(true);
  });

  it("keeps an alert of its own on a Mac, where that command has no program to run", () => {
    expect(daemonTells("#app", memory(), MAC)).toBe(false);
  });

  it("is never told by the daemon in a browser tab", () => {
    expect(daemonTells("", memory(), LINUX)).toBe(false);
  });
});
