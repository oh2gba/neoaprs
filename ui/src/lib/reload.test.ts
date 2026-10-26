import { afterEach, describe, expect, it, vi } from "vitest";
import { pageBuild } from "@/lib/build";
import { currentPage, describeMismatch, matches, reloadForDaemon } from "@/lib/reload";
import { PROTOCOL } from "@/protocol/lists";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  sessionStorage.clear();
});

const page = { protocol: PROTOCOL, page: "index-AAAA.js" };
const hello = (extra: { version?: string; protocol?: number; page?: string } = {}) => ({
  protocol: PROTOCOL,
  version: "0.3.0",
  page: "index-AAAA.js",
  ...extra,
});

describe("what matches", () => {
  it("is the protocol and the build, never the version of NeoAPRS", () => {
    expect(matches(hello(), page)).toBe(true);
    expect(matches(hello({ version: "7.0.0" }), page)).toBe(true);
    expect(matches(hello({ protocol: PROTOCOL + 1 }), page)).toBe(false);
    expect(matches(hello({ page: "index-BBBB.js" }), page)).toBe(false);
  });

  it("does not compare builds when either side does not know its own (development, a daemon without a built page)", () => {
    expect(matches(hello({ page: "index-BBBB.js" }), { ...page, page: "" })).toBe(true);
    expect(matches(hello({ page: "" }), page)).toBe(true);
    expect(matches({ protocol: PROTOCOL, version: "0.3.0" }, page)).toBe(true);
    expect(matches(hello({ protocol: PROTOCOL + 1, page: "" }), { ...page, page: "" })).toBe(false);
  });

  it("knows the page's identity from the protocol it was generated with and the main script its document loaded", () => {
    const doc = document.implementation.createHTMLDocument("t");
    doc.head.innerHTML =
      '<script type="module" crossorigin src="./assets/index-DefyaO5x.js"></script><script type="module" src="./assets/other-1.js"></script>';
    expect(pageBuild(doc)).toBe("index-DefyaO5x.js");
    expect(pageBuild(document.implementation.createHTMLDocument("none"))).toBe("");
    expect(currentPage()).toEqual({ protocol: PROTOCOL, page: "" });
  });

  it("describes both sides for the notice as identifiers: the build and protocol of the page, the version, build and protocol of the daemon", () => {
    expect(describeMismatch(hello({ version: "0.9.2", protocol: 13, page: "index-BBBB.js" }), { protocol: 12, page: "index-AAAA.js" })).toEqual({
      page: "index-AAAA.js/12",
      neoaprs: "0.9.2, index-BBBB.js/13",
    });
    expect(describeMismatch({ protocol: 12, version: "0.9.2" }, { protocol: 12, page: "" })).toEqual({ page: "-/12", neoaprs: "0.9.2, -/12" });
  });
});

describe("reloadForDaemon", () => {
  it("loads the page again when the daemon serves another build of the page", () => {
    const reload = vi.fn();
    expect(reloadForDaemon(hello({ page: "index-BBBB.js" }), page, reload)).toBe("reload");
    expect(reload).toHaveBeenCalledOnce();
  });

  it("loads the page again when the daemon speaks another protocol", () => {
    const reload = vi.fn();
    expect(reloadForDaemon(hello({ protocol: PROTOCOL + 1 }), page, reload)).toBe("reload");
    expect(reload).toHaveBeenCalledOnce();
  });

  it("does nothing when the daemon is of the page's protocol and build, whatever its version", () => {
    const reload = vi.fn();
    expect(reloadForDaemon(hello(), page, reload)).toBe("same");
    expect(reloadForDaemon(hello({ version: "1.0.0" }), page, reload)).toBe("same");
    expect(reload).not.toHaveBeenCalled();
  });

  it("does not load again when it still differs after the load: that is `stale`, which the page shows as a notice", () => {
    const reload = vi.fn();
    const other = hello({ page: "index-BBBB.js" });
    expect(reloadForDaemon(other, page, reload)).toBe("reload");
    expect(reloadForDaemon(other, page, reload)).toBe("stale");
    expect(reloadForDaemon(other, page, reload)).toBe("stale");
    expect(reload).toHaveBeenCalledOnce();
  });

  it("loads again for a later update once a hello has matched", () => {
    const reload = vi.fn();
    reloadForDaemon(hello({ page: "index-BBBB.js" }), page, reload);
    expect(reloadForDaemon(hello(), page, reload)).toBe("same");
    expect(reloadForDaemon(hello({ page: "index-BBBB.js" }), page, reload)).toBe("reload");
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("loads again for a daemon that is not the one it loaded for, once for each", () => {
    const reload = vi.fn();
    expect(reloadForDaemon(hello({ page: "index-BBBB.js" }), page, reload)).toBe("reload");
    expect(reloadForDaemon(hello({ page: "index-CCCC.js" }), page, reload)).toBe("reload");
    expect(reloadForDaemon(hello({ page: "index-CCCC.js" }), page, reload)).toBe("stale");
    expect(reloadForDaemon(hello({ page: "index-CCCC.js", version: "0.9.3" }), page, reload)).toBe("reload");
    expect(reload).toHaveBeenCalledTimes(3);
  });

  it("does not load by itself when the browser keeps no session storage, which could go on for ever: the notice and its button are what is left", () => {
    const reload = vi.fn();
    const blocked = () => {
      throw new Error("blocked");
    };
    vi.stubGlobal("sessionStorage", { getItem: blocked, setItem: blocked, removeItem: blocked });
    expect(reloadForDaemon(hello({ page: "index-BBBB.js" }), page, reload)).toBe("stale");
    expect(reload).not.toHaveBeenCalled();
  });

  it("loads the page itself with location.reload when no function is given, for a page of its own identity", () => {
    const reload = vi.fn();
    vi.stubGlobal("location", { ...window.location, reload });
    expect(reloadForDaemon(hello({ protocol: PROTOCOL + 1 }))).toBe("reload");
    expect(reload).toHaveBeenCalledOnce();
  });
});
