import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SettingsAbout from "@/components/SettingsAbout.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { en } from "@/i18n/en";
import { LOCALES } from "@/i18n/locales";
import { pageErrors } from "@/lib/pageerrors";
import { LIMITS } from "@/protocol/lists";
import { fakeDaemon, withDaemon } from "@/test/context";

function make(version = "0.9.1") {
  return makeWith({ version });
}

function makeWith(over = {}) {
  return mount(SettingsAbout, { global: withDaemon(fakeDaemon({ version: "0.9.1", call: "OH2GBA", ...over })) });
}

const ZIP = { "Content-Type": "application/zip", "Content-Disposition": 'attachment; filename="neoaprs-support-OH2GBA-20261021-123456Z.zip"' };

/** The fetch of the page: `answer` is what the daemon says to the next request, kept with what was asked. */
function daemonSays(answer: () => Promise<Response>) {
  const fetcher = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => answer());
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

const downloads: { href: string; download: string }[] = [];

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the About group", () => {
  it("says what NeoAPRS is with the daemon's version, who made it, and has one control: Download logs, a link on the last line", () => {
    const wrapper = make();
    expect(wrapper.find("legend").text()).toBe("About");
    expect(wrapper.findAll("p")[0]?.text()).toBe("NeoAPRS 0.9.1, an APRS client for your radio, on VHF and over HF. Made by OH2GBA, 2026.");
    const controls = wrapper.findAll("button:not(.groupfold), input, select");
    expect(controls.map((c) => [c.text(), c.classes()])).toEqual([["Download logs", ["linkbtn"]]]);
    const paragraphs = wrapper.findAll("p");
    expect(paragraphs[paragraphs.length - 1]?.classes()).toContain("about-download");
  });

  it("shows the version the daemon reports", () => {
    expect(make("1.2.3").text()).toContain("NeoAPRS 1.2.3,");
  });

  it("says the year the project began, 2026, whatever year it is now", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2031-06-01T12:00:00Z"));
    expect(make().findAll("p")[0]?.text()).toContain("Made by OH2GBA, 2026.");
  });

  it("has the licence and the source as links that open in a new tab", () => {
    const wrapper = make();
    expect(wrapper.text()).toContain("Free software under the GNU General Public License, version 3 or later.");
    const [license, source] = wrapper.findAll("a");
    expect(license?.text()).toBe("GNU General Public License");
    expect(license?.attributes("href")).toBe("https://www.gnu.org/licenses/gpl-3.0.html");
    expect(source?.text()).toBe("Source code");
    expect(source?.attributes("href")).toBe("https://github.com/oh2gba/neoaprs");
    expect(wrapper.findAll("a")).toHaveLength(5); // (the licence, the source, the modem, and the two of the feedback line)
    for (const link of [license, source]) {
      expect(link?.attributes("target")).toBe("_blank");
      expect(link?.attributes("rel")).toContain("noopener");
    }
  });

  it("names the HF modem and the version of it that is built in, its name a link to its source that opens in a new tab", () => {
    const wrapper = make();
    const line = wrapper.findAll("p")[3];
    expect(line?.text()).toBe(`The HF modem is Mercury ${LIMITS.mercury.version} by Rhizomatica.`);
    expect(LIMITS.mercury.version).toMatch(/^\d+\.\d+\.\d+$/);
    const link = line?.get("a");
    expect(link?.text()).toBe(`Mercury ${LIMITS.mercury.version}`);
    expect(link?.attributes("href")).toBe("https://github.com/Rhizomatica/mercury");
    expect(link?.attributes("target")).toBe("_blank");
    expect(link?.attributes("rel")).toContain("noopener");
  });

  it("thanks everyone who tried it and sent feedback, and names no one", () => {
    const wrapper = make();
    expect(wrapper.get("p.muted").text()).toBe("Thanks to everyone who tried it and sent feedback.");
    expect(wrapper.text()).not.toMatch(/OH2GAX|OH2DPN|OH7NFC/);
    expect(wrapper.findAll(".mono")).toHaveLength(0);
  });
});

describe("the feedback line", () => {
  it("says ideas and bug reports can also go to GitHub issues or the address, both links, under the thanks line (Send feedback / logs of Help is the way first)", () => {
    const wrapper = make();
    const paragraphs = wrapper.findAll("p");
    const line = paragraphs[paragraphs.length - 2];
    expect(line?.text()).toBe("Ideas and bug reports can also go to GitHub issues or neoaprs@oh2gba.eu.");
    const links = line?.findAll("a");
    expect(links?.map((a) => a.attributes("href"))).toEqual(["https://github.com/oh2gba/neoaprs/issues", "mailto:neoaprs@oh2gba.eu"]);
    expect(links?.[0]?.attributes("target")).toBe("_blank");
    expect(wrapper.get("p.muted").element.nextElementSibling).toBe(line?.element);
  });
});

describe("the About group in the Settings tab", () => {
  it("is the last group, after Help, and the My station tab has none", () => {
    const settings = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon() });
    const titles = settings.findAll("form > fieldset").map((f) => f.find("legend").text());
    expect(titles.slice(-2)).toEqual(["Help", "About"]);
    const beacon = mount(SettingsForm, { props: { scope: "beacon" }, global: withDaemon() });
    expect(beacon.find(".about").exists()).toBe(false);
  });
});

describe("the words of the group in every language", () => {
  const english = en as Record<string, unknown>;
  const ids = Object.keys(english).filter((id) => id.startsWith("settings.about."));

  it("has the nine ids of the group in English", () => {
    expect(ids).toHaveLength(9);
  });

  for (const locale of LOCALES.filter((l) => l.code !== "en")) {
    it(`${locale.name} has every one, translated, with the values and the places where English has them`, () => {
      const messages = locale.messages as Record<string, unknown>;
      for (const id of ids) {
        const text = String(messages[id]);
        const source = String(english[id]);
        expect(text, id).not.toBe("undefined");
        // the name of the licence is kept in German and Dutch as it is written there
        if (!(["de", "nl"].includes(locale.code) && id === "settings.about.license_link")) expect(text, id).not.toBe(source);
        for (const name of source.match(/\{\w+\}/g) ?? []) expect(text, id).toContain(name);
      }
    });
  }
});

describe("the typography of the group in French and Italian", () => {
  const texts = (code: string): string[] => {
    const messages = LOCALES.find((l) => l.code === code)?.messages as Record<string, string>;
    return Object.keys(messages)
      .filter((id) => id.startsWith("settings.about."))
      .map((id) => messages[id]);
  };

  it("French has a no-break space before : ; ? ! and %, never a plain one", () => {
    for (const text of texts("fr")) expect(text).not.toMatch(/ [:;?!%]/);
    const fr = LOCALES.find((l) => l.code === "fr")?.messages as Record<string, string>;
    expect(fr["settings.help.text"]).toContain("problème\u00a0? ");
  });

  it("Italian writes its apostrophe curly", () => {
    for (const text of texts("it")) expect(text).not.toContain("'");
    expect(texts("it").join(" ")).toContain("l\u2019hanno");
  });
});

describe("Download logs, the last line", () => {
  beforeEach(() => {
    downloads.length = 0;
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:support"), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      downloads.push({ href: this.href, download: this.download });
    });
  });

  it("reads Collecting… and is disabled while the file is made, and asks only once", async () => {
    let finish: (response: Response) => void = () => undefined;
    const fetcher = daemonSays(() => new Promise<Response>((resolve) => (finish = resolve)));
    const wrapper = make();
    await wrapper.get("#set-help-logs").trigger("click");
    expect(wrapper.get("#set-help-logs").text()).toBe("Collecting…");
    expect(wrapper.get("#set-help-logs").attributes("disabled")).toBeDefined();
    await wrapper.get("#set-help-logs").trigger("click");
    expect(fetcher).toHaveBeenCalledTimes(1);
    finish(new Response("PK", { status: 200, headers: ZIP }));
    await flushPromises();
    expect(wrapper.get("#set-help-logs").text()).toBe("Download logs");
    expect(wrapper.get("#set-help-logs").attributes("disabled")).toBeUndefined();
  });

  it("posts the page's info as {page: ...} beside the page, with the ring of errors in it", async () => {
    pageErrors.record(new Error("seen before the press"), "window");
    const fetcher = daemonSays(() => Promise.resolve(new Response("PK", { status: 200, headers: ZIP })));
    const wrapper = makeWith({ connection: "open" });
    await wrapper.get("#set-help-logs").trigger("click");
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
        "viewport",
      ].sort(),
    );
    expect(body.page).toMatchObject({ daemonVersion: "0.9.1", connection: "open" });
    expect(JSON.stringify(body.page["errors"])).toContain("seen before the press");
    expect(typeof body.page["timeMs"]).toBe("number");
    expect(String(body.page["time"])).toMatch(/Z$/);
  });

  it("saves the zip under the daemon's name and says so quietly on the same line", async () => {
    daemonSays(() => Promise.resolve(new Response("PK", { status: 200, headers: ZIP })));
    const wrapper = make();
    await wrapper.get("#set-help-logs").trigger("click");
    await flushPromises();
    expect(downloads).toEqual([{ href: "blob:support", download: "neoaprs-support-OH2GBA-20261021-123456Z.zip" }]);
    expect(wrapper.get(".about-download").text()).toBe("Download logs · Saved neoaprs-support-OH2GBA-20261021-123456Z.zip.");
    expect(wrapper.find(".about-download .field-error").exists()).toBe(false);
  });

  it("makes a name from the call and the time when the daemon gave none", async () => {
    daemonSays(() => Promise.resolve(new Response("PK", { status: 200 })));
    const wrapper = make();
    await wrapper.get("#set-help-logs").trigger("click");
    await flushPromises();
    expect(downloads[0]?.download).toMatch(/^neoaprs-support-OH2GBA-\d{8}-\d{6}Z\.zip$/);
  });

  it.each([
    [403, "No access: reload the page, enter the access key and try again."],
    [401, "No access: reload the page, enter the access key and try again."],
    [429, "Another file is being made. Try again in a minute."],
    [500, "The file could not be made (error 500)."],
  ])("says in plain words what a %i means, and no file is named", async (status, text) => {
    daemonSays(() => Promise.resolve(new Response(null, { status })));
    const wrapper = make();
    await wrapper.get("#set-help-logs").trigger("click");
    await flushPromises();
    expect(wrapper.get(".about-download .field-error").text()).toBe(text);
    expect(wrapper.get(".about-download").text()).not.toContain("Saved");
    expect(downloads).toEqual([]);
    expect(wrapper.get("#set-help-logs").attributes("disabled")).toBeUndefined();
  });

  it("says the daemon cannot be reached when there is no answer, and takes the words back at the next try", async () => {
    daemonSays(() => Promise.reject(new TypeError("network")));
    const wrapper = make();
    await wrapper.get("#set-help-logs").trigger("click");
    await flushPromises();
    expect(wrapper.get(".about-download").text()).toBe("Download logs · The daemon could not be reached.");
    daemonSays(() => Promise.resolve(new Response("PK", { status: 200, headers: ZIP })));
    await wrapper.get("#set-help-logs").trigger("click");
    await flushPromises();
    expect(wrapper.find(".field-error").exists()).toBe(false);
    expect(wrapper.get(".about-download").text()).toContain("Saved");
  });
});
