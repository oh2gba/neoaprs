import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import SettingsHelp from "@/components/SettingsHelp.vue";
import { en } from "@/i18n/en";
import { LOCALES } from "@/i18n/locales";
import { PAGE_VERSION } from "@/lib/build";
import { pageErrors } from "@/lib/pageerrors";
import { fakeDaemon, withDaemon } from "@/test/context";

const ZIP = { "Content-Type": "application/zip", "Content-Disposition": 'attachment; filename="neoaprs-support-OH2GBA-20261021-123456Z.zip"' };

/** The fetch of the page: `answer` is what the daemon says to the next request, kept with what was asked. */
function daemonSays(answer: () => Promise<Response>) {
  const fetcher = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => answer());
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const downloads: { href: string; download: string }[] = [];

beforeEach(() => {
  downloads.length = 0;
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:support"), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    downloads.push({ href: this.href, download: this.download });
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function make(over = {}) {
  return mount(SettingsHelp, { global: withDaemon(fakeDaemon({ call: "OH2GBA", version: "0.9.0", ...over })) });
}

describe("the Help group", () => {
  it("has the short text, one plain button, one quiet line about the file and the link to the manual", () => {
    const wrapper = make();
    expect(wrapper.find("legend").text()).toBe("Help");
    expect(wrapper.text()).toContain(
      "Something not working? Download the logs and e-mail them to neoaprs@oh2gba.eu with a few words: what you did, what you expected, what happened, and roughly when.",
    );
    const button = wrapper.get("button");
    expect(wrapper.findAll("button")).toHaveLength(1);
    expect(button.text()).toBe("Download logs");
    expect(button.classes()).toEqual(["btn"]);
    expect(button.attributes("disabled")).toBeUndefined();
    expect(wrapper.get(".muted").text()).toBe(
      "The file holds the log, the settings without the access key, and the packets heard and sent. NeoAPRS sends nothing by itself.",
    );
    const manual = wrapper.get("a");
    expect(manual.text()).toBe("What is in the file");
    expect(manual.attributes("href")).toBe("https://github.com/oh2gba/neoaprs/blob/master/docs/manual/support.md");
    expect(manual.attributes("target")).toBe("_blank");
    expect(manual.attributes("rel")).toContain("noopener");
    expect(wrapper.find(".help-result").text()).toBe("");
  });

  it("reads Collecting… and is disabled while the file is made, and asks only once", async () => {
    let finish: (response: Response) => void = () => undefined;
    const fetcher = daemonSays(() => new Promise<Response>((resolve) => (finish = resolve)));
    const wrapper = make();
    await wrapper.get("button").trigger("click");
    expect(wrapper.get("button").text()).toBe("Collecting…");
    expect(wrapper.get("button").attributes("disabled")).toBeDefined();
    await wrapper.get("button").trigger("click");
    expect(fetcher).toHaveBeenCalledTimes(1);
    finish(new Response("PK", { status: 200, headers: ZIP }));
    await flushPromises();
    expect(wrapper.get("button").text()).toBe("Download logs");
    expect(wrapper.get("button").attributes("disabled")).toBeUndefined();
  });

  it("posts the page's info as {page: ...} beside the page, with the ring of errors in it", async () => {
    pageErrors.record(new Error("seen before the press"), "window");
    const fetcher = daemonSays(() => Promise.resolve(new Response("PK", { status: 200, headers: ZIP })));
    const wrapper = make({ connection: "open" });
    await wrapper.get("button").trigger("click");
    await flushPromises();
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:7303/support/bundle");
    expect(init).toMatchObject({ method: "POST", credentials: "same-origin" });
    const body = JSON.parse(typeof init?.body === "string" ? init.body : "") as { page: Record<string, unknown> };
    expect(Object.keys(body)).toEqual(["page"]);
    expect(Object.keys(body.page).sort()).toEqual(
      [
        "build",
        "connection",
        "daemonVersion",
        "darkScheme",
        "errors",
        "language",
        "panelWidth",
        "serviceWorkerControlled",
        "sizeClass",
        "standalone",
        "time",
        "timeMs",
        "timeZone",
        "userAgent",
        "version",
        "viewport",
      ].sort(),
    );
    expect(body.page).toMatchObject({ version: PAGE_VERSION, daemonVersion: "0.9.0", connection: "open" });
    expect(JSON.stringify(body.page["errors"])).toContain("seen before the press");
    expect(typeof body.page["timeMs"]).toBe("number");
    expect(String(body.page["time"])).toMatch(/Z$/);
  });

  it("saves the zip under the daemon's name, says so quietly and offers the e-mail with the version and a form", async () => {
    daemonSays(() => Promise.resolve(new Response("PK", { status: 200, headers: ZIP })));
    const wrapper = make();
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(downloads).toEqual([{ href: "blob:support", download: "neoaprs-support-OH2GBA-20261021-123456Z.zip" }]);
    expect(wrapper.get(".help-result .muted").text()).toBe("Saved neoaprs-support-OH2GBA-20261021-123456Z.zip.");
    const write = wrapper.get(".help-result a");
    expect(write.text()).toBe("Write to neoaprs@oh2gba.eu");
    const url = new URL(write.attributes("href") ?? "");
    expect(url.protocol).toBe("mailto:");
    expect(url.pathname).toBe("neoaprs@oh2gba.eu");
    expect(url.searchParams.get("subject")).toBe(`NeoAPRS ${PAGE_VERSION}: `);
    expect(url.searchParams.get("body")).toBe(
      [
        "What I did:",
        "",
        "What I expected:",
        "",
        "What happened:",
        "",
        "When (roughly):",
        "",
        "Remember to attach neoaprs-support-OH2GBA-20261021-123456Z.zip.",
      ].join("\r\n"),
    );
    expect(wrapper.find(".field-error").exists()).toBe(false);
  });

  it("makes a name from the call and the time when the daemon gave none", async () => {
    daemonSays(() => Promise.resolve(new Response("PK", { status: 200 })));
    const wrapper = make();
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(downloads[0]?.download).toMatch(/^neoaprs-support-OH2GBA-\d{8}-\d{6}Z\.zip$/);
  });

  it.each([
    [403, "No access: reload the page, enter the access key and try again."],
    [401, "No access: reload the page, enter the access key and try again."],
    [429, "Another file is being made. Try again in a minute."],
    [500, "The file could not be made (error 500)."],
  ])("says in plain words what a %i means, and offers no e-mail", async (status, text) => {
    daemonSays(() => Promise.resolve(new Response(null, { status })));
    const wrapper = make();
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get(".help-result .field-error").text()).toBe(text);
    expect(wrapper.find(".help-result a").exists()).toBe(false);
    expect(downloads).toEqual([]);
    expect(wrapper.get("button").attributes("disabled")).toBeUndefined();
  });

  it("says the daemon cannot be reached when there is no answer, and takes the words back at the next try", async () => {
    daemonSays(() => Promise.reject(new TypeError("network")));
    const wrapper = make();
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.get(".help-result").text()).toBe("The daemon could not be reached.");
    daemonSays(() => Promise.resolve(new Response("PK", { status: 200, headers: ZIP })));
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(wrapper.find(".field-error").exists()).toBe(false);
    expect(wrapper.get(".help-result .muted").text()).toContain("Saved");
  });
});

describe("the Help group in the Settings tab", () => {
  it("is the group before About, after Update check, and the Beacon tab has none", () => {
    const settings = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon() });
    const titles = settings.findAll("form > fieldset").map((f) => f.find("legend").text());
    expect(titles.slice(-3)).toEqual(["Update check", "Help", "About"]);
    const beacon = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon() });
    expect(beacon.find(".help-logs").exists()).toBe(false);
  });
});

describe("the words of the group in every language", () => {
  const english = en as Record<string, unknown>;
  const ids = Object.keys(english).filter((id) => id.startsWith("settings.help."));

  it("has the ids of the group in English", () => {
    expect(ids.length).toBeGreaterThanOrEqual(17);
  });

  for (const locale of LOCALES.filter((l) => l.code !== "en")) {
    it(`${locale.name} has every one, translated, with the address and the file where English has them`, () => {
      const messages = locale.messages as Record<string, unknown>;
      for (const id of ids) {
        const text = String(messages[id]);
        const source = String(english[id]);
        expect(text, id).not.toBe("undefined");
        expect(text, id).not.toBe(source);
        for (const name of source.match(/\{\w+\}/g) ?? []) expect(text, id).toContain(name);
      }
    });
  }
});
