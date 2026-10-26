import { afterEach, describe, expect, it, vi } from "vitest";
import type { PageErrorEntry } from "@/lib/pageerrors";
import {
  BODY_MAX_BYTES,
  bodyOf,
  filenameOf,
  madeName,
  mailtoLink,
  pageInfo,
  requestBundle,
  saveFile,
  type InfoGiven,
  type InfoHost,
  type PageInfo,
} from "@/lib/support";

const NOW = Date.parse("2026-10-21T12:34:56Z");

function host(over: Partial<InfoHost> = {}): InfoHost {
  return {
    navigator: { userAgent: "Mozilla/5.0 (X11; Linux) Test", language: "fi-FI" },
    innerWidth: 390,
    innerHeight: 800,
    matchMedia: (query) => ({ matches: query === "(prefers-color-scheme: dark)" }),
    document,
    ...over,
  };
}

const given: InfoGiven = { panelWidth: 480, connection: "open", daemonVersion: "0.9.0", errors: [] };
const entry = (n: number, stack = "s"): PageErrorEntry => ({
  message: `e${n}`,
  stack,
  source: "vue",
  at: "2026-10-21T12:00:00.000Z",
  last: "2026-10-21T12:00:00.000Z",
  count: 0,
  component: "",
});

describe("pageInfo", () => {
  it("has the facts of the page and the browser", () => {
    expect(pageInfo({ ...given, errors: [entry(1)] }, host(), NOW)).toEqual({
      build: "",
      daemonVersion: "0.9.0",
      userAgent: "Mozilla/5.0 (X11; Linux) Test",
      language: "fi-FI",
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      timeMs: NOW,
      time: "2026-10-21T12:34:56.000Z",
      viewport: { width: 390, height: 800 },
      panelWidth: 480,
      sizeClass: "phone",
      darkScheme: true,
      standalone: false,
      serviceWorkerControlled: false,
      connection: "open",
      errors: [entry(1)],
    });
  });

  it("knows an installed page (display mode, or Safari's flag) and a controlling worker", () => {
    const app = host({
      matchMedia: (query) => ({ matches: query === "(display-mode: standalone)" }),
      navigator: { userAgent: "u", language: "en", serviceWorker: { controller: {} } },
    });
    expect(pageInfo(given, app, NOW)).toMatchObject({ standalone: true, darkScheme: false, serviceWorkerControlled: true });
    const safari = host({ matchMedia: undefined, navigator: { userAgent: "u", language: "en", standalone: true, serviceWorker: { controller: null } } });
    expect(pageInfo(given, safari, NOW)).toMatchObject({ standalone: true, darkScheme: false, serviceWorkerControlled: false });
  });

  it("names the size class by the window: tablet and desktop", () => {
    expect(pageInfo(given, host({ innerWidth: 900, innerHeight: 900 }), NOW).sizeClass).toBe("tablet");
    expect(pageInfo(given, host({ innerWidth: 1500, innerHeight: 900 }), NOW).sizeClass).toBe("desktop");
  });
});

describe("bodyOf", () => {
  const info = (errors: PageErrorEntry[]): PageInfo => pageInfo({ ...given, errors }, host(), NOW);

  it("is the page's info under the key page", () => {
    expect((JSON.parse(bodyOf(info([entry(1)]))) as { page: unknown }).page).toEqual(JSON.parse(JSON.stringify(info([entry(1)]))) as unknown);
  });

  it("stays under the daemon's limit: the stacks are cut first, then the oldest errors go", () => {
    const many = Array.from({ length: 50 }, (_, n) => entry(n, "x".repeat(8000)));
    const body = bodyOf(info(many));
    expect(new TextEncoder().encode(body).length).toBeLessThanOrEqual(BODY_MAX_BYTES);
    const kept = (JSON.parse(body) as { page: PageInfo }).page.errors;
    expect(kept.at(-1)?.message).toBe("e49");
    const huge = Array.from({ length: 50 }, (_, n) => ({ ...entry(n), message: "m".repeat(2000), stack: "x".repeat(8000) }));
    const cut = bodyOf(info(huge));
    expect(new TextEncoder().encode(cut).length).toBeLessThanOrEqual(BODY_MAX_BYTES);
    expect((JSON.parse(cut) as { page: PageInfo }).page.errors.at(-1)?.message).toBe("m".repeat(2000));
  });
});

describe("the file name", () => {
  it("is the daemon's, kept to plain characters", () => {
    expect(filenameOf('attachment; filename="neoaprs-support-OH2GBA-20261021-123456Z.zip"')).toBe("neoaprs-support-OH2GBA-20261021-123456Z.zip");
    expect(filenameOf("attachment; filename=a.zip")).toBe("a.zip");
    expect(filenameOf('attachment; filename="../../etc/pass wd.zip"')).toBe("pass_wd.zip");
    expect(filenameOf("attachment")).toBeNull();
    expect(filenameOf(null)).toBeNull();
    expect(filenameOf('attachment; filename=".."')).toBeNull();
  });

  it("is made the same way when the daemon gave none", () => {
    expect(madeName("OH2GBA-9", NOW)).toBe("neoaprs-support-OH2GBA-9-20261021-123456Z.zip");
    expect(madeName(null, NOW)).toBe("neoaprs-support-20261021-123456Z.zip");
  });
});

describe("requestBundle", () => {
  const info = pageInfo(given, host(), NOW);
  const answer = (status: number, headers: Record<string, string> = {}, body = "PK") =>
    vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => Promise.resolve(new Response(status === 200 ? body : null, { status, headers })));

  it("posts the page's info as JSON to support/bundle beside the page, with the page's credentials", async () => {
    const fetcher = answer(200, { "Content-Disposition": 'attachment; filename="f.zip"', "Content-Type": "application/zip" });
    const bundle = await requestBundle(info, "OH2GBA", fetcher, NOW);
    expect(bundle).toMatchObject({ ok: true, filename: "f.zip" });
    expect(bundle.ok && (await bundle.blob.text())).toBe("PK");
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:7303/support/bundle");
    expect(init).toMatchObject({ method: "POST", credentials: "same-origin", cache: "no-store", headers: { "Content-Type": "application/json" } });
    expect(JSON.parse(typeof init?.body === "string" ? init.body : "")).toEqual({ page: JSON.parse(JSON.stringify(info)) as unknown });
  });

  it("makes a name when the answer has none", async () => {
    expect(await requestBundle(info, "OH2GBA", answer(200), NOW)).toMatchObject({ ok: true, filename: "neoaprs-support-OH2GBA-20261021-123456Z.zip" });
  });

  it("names the problem: no access (401, 403), busy (429), the daemon not reachable, and any other answer", async () => {
    expect(await requestBundle(info, null, answer(401), NOW)).toEqual({ ok: false, problem: "access", status: 401 });
    expect(await requestBundle(info, null, answer(403), NOW)).toEqual({ ok: false, problem: "access", status: 403 });
    expect(await requestBundle(info, null, answer(429), NOW)).toEqual({ ok: false, problem: "busy", status: 429 });
    expect(await requestBundle(info, null, answer(500), NOW)).toEqual({ ok: false, problem: "failed", status: 500 });
    expect(
      await requestBundle(
        info,
        null,
        vi.fn(() => Promise.reject(new TypeError("network"))),
        NOW,
      ),
    ).toEqual({ ok: false, problem: "unreachable", status: 0 });
  });
});

describe("saveFile", () => {
  afterEach(() => vi.useRealTimers());

  it("clicks a link that downloads the file, takes it away, and gives the object URL back after a moment", () => {
    vi.useFakeTimers();
    const urls = { createObjectURL: vi.fn(() => "blob:abc"), revokeObjectURL: vi.fn() };
    const clicked: { href: string; download: string; inDocument: boolean }[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({ href: this.href, download: this.download, inDocument: document.body.contains(this) });
    });
    saveFile(new Blob(["PK"]), "f.zip", document, urls);
    expect(clicked).toEqual([{ href: "blob:abc", download: "f.zip", inDocument: true }]);
    expect(document.querySelector("a[download]")).toBeNull();
    expect(urls.revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(urls.revokeObjectURL).toHaveBeenCalledWith("blob:abc");
    click.mockRestore();
  });
});

describe("mailtoLink", () => {
  it("is to the project, with the daemon's version in the subject and a form in the body", () => {
    const link = mailtoLink(["What I did:", "What I expected:"], "Remember to attach f.zip.", "0.9.0");
    const url = new URL(link);
    expect(url.protocol).toBe("mailto:");
    expect(url.pathname).toBe("neoaprs@oh2gba.eu");
    expect(url.searchParams.get("subject")).toBe("NeoAPRS 0.9.0: ");
    expect(url.searchParams.get("body")).toBe("What I did:\r\n\r\nWhat I expected:\r\n\r\nRemember to attach f.zip.");
  });
});
