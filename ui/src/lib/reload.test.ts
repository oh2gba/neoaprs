import { afterEach, describe, expect, it, vi } from "vitest";
import { PAGE_VERSION, pageBuild } from "@/lib/build";
import { reloadForDaemon } from "@/lib/reload";
import { PROTOCOL } from "@/protocol/lists";

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

const page = { protocol: PROTOCOL, version: "0.3.0" };
const hello = (version: string, protocol = PROTOCOL) => ({ protocol, version });

describe("reloadForDaemon", () => {
  it("is built with the version of the package", () => {
    expect(PAGE_VERSION).toMatch(/^\d+\.\d+\.\d+/);
  });

  it("loads the page again when the daemon is of another version", () => {
    const reload = vi.fn();
    expect(reloadForDaemon(hello("0.4.0"), page, reload)).toBe("reload");
    expect(reload).toHaveBeenCalledOnce();
  });

  it("loads the page again when the daemon speaks another protocol of the same version", () => {
    const reload = vi.fn();
    expect(reloadForDaemon(hello("0.3.0", PROTOCOL + 1), page, reload)).toBe("reload");
    expect(reload).toHaveBeenCalledOnce();
  });

  it("does nothing when the daemon is the page's version", () => {
    const reload = vi.fn();
    expect(reloadForDaemon(hello("0.3.0"), page, reload)).toBe("same");
    expect(reload).not.toHaveBeenCalled();
  });

  it("does not load again when the version still differs after the load", () => {
    const reload = vi.fn();
    expect(reloadForDaemon(hello("0.4.0"), page, reload)).toBe("reload");
    expect(reloadForDaemon(hello("0.4.0"), page, reload)).toBe("stale");
    expect(reloadForDaemon(hello("0.4.0"), page, reload)).toBe("stale");
    expect(reload).toHaveBeenCalledOnce();
  });

  it("loads again for a later update once a hello has matched", () => {
    const reload = vi.fn();
    reloadForDaemon(hello("0.4.0"), page, reload);
    expect(reloadForDaemon(hello("0.3.0"), page, reload)).toBe("same");
    expect(reloadForDaemon(hello("0.4.0"), page, reload)).toBe("reload");
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("loads again for a newer version than the one it loaded for", () => {
    const reload = vi.fn();
    reloadForDaemon(hello("0.4.0"), page, reload);
    expect(reloadForDaemon(hello("0.5.0"), page, reload)).toBe("reload");
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("loads the page again when the daemon serves another build of the same version, once for each build", () => {
    const reload = vi.fn();
    const built = { ...page, page: "index-AAAA.js" };
    expect(reloadForDaemon({ ...hello("0.3.0"), page: "index-AAAA.js" }, built, reload)).toBe("same");
    expect(reloadForDaemon({ ...hello("0.3.0"), page: "index-BBBB.js" }, built, reload)).toBe("reload");
    expect(reloadForDaemon({ ...hello("0.3.0"), page: "index-BBBB.js" }, built, reload)).toBe("stale");
    expect(reloadForDaemon({ ...hello("0.3.0"), page: "index-CCCC.js" }, built, reload)).toBe("reload");
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("does not compare builds when either side does not know its own (development, a daemon without a built page)", () => {
    const reload = vi.fn();
    expect(reloadForDaemon({ ...hello("0.3.0"), page: "index-BBBB.js" }, { ...page, page: "" }, reload)).toBe("same");
    expect(reloadForDaemon({ ...hello("0.3.0"), page: "" }, { ...page, page: "index-AAAA.js" }, reload)).toBe("same");
    expect(reload).not.toHaveBeenCalled();
  });

  it("knows its build from the main script its document loaded", () => {
    const doc = document.implementation.createHTMLDocument("t");
    doc.head.innerHTML =
      '<script type="module" crossorigin src="./assets/index-DefyaO5x.js"></script><script type="module" src="./assets/other-1.js"></script>';
    expect(pageBuild(doc)).toBe("index-DefyaO5x.js");
    expect(pageBuild(document.implementation.createHTMLDocument("none"))).toBe("");
  });

  it("carries on when the browser keeps no session storage", () => {
    const reload = vi.fn();
    const blocked = () => {
      throw new Error("blocked");
    };
    vi.stubGlobal("sessionStorage", { getItem: blocked, setItem: blocked, removeItem: blocked });
    expect(reloadForDaemon(hello("0.4.0"), page, reload)).toBe("stale");
    expect(reload).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("loads the page itself with location.reload when no function is given", () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    expect(reloadForDaemon(hello("9.9.9"))).toBe("reload");
    expect(reload).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });
});
