import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import PopupHelp from "@/components/PopupHelp.vue";
import { openedAt, resetSeen } from "@/test/fakealert";

const FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0";
const FIREFOX_WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0";
const CHROME = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";
const EDGE = `${CHROME} Edg/140.0.0.0`;
const OPERA = `${CHROME} OPR/120.0.0.0`;
const ANDROID_CHROME = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36";
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const SAFARI = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15";

const writeText = vi.fn(() => Promise.resolve());

function panel(userAgent: string, host = "neoaprs-pi.local", extra: Record<string, unknown> = {}) {
  vi.stubGlobal("navigator", { userAgent, clipboard: { writeText }, ...extra });
  openedAt(host);
  return mount(PopupHelp);
}

const steps = (wrapper: ReturnType<typeof panel>) => wrapper.findAll("ol li").map((li) => li.text());
const copyButton = (wrapper: ReturnType<typeof panel>, n: number) => wrapper.findAll(".copyfield button")[n];

afterEach(() => {
  vi.unstubAllGlobals();
  resetSeen();
  writeText.mockClear();
});

describe("the steps to allow pop-ups", () => {
  it("gives Firefox four steps, with the host to put in", () => {
    const wrapper = panel(FIREFOX_WINDOWS);
    expect(wrapper.find("h4").text()).toBe("Enable pop-ups in Firefox");
    expect(steps(wrapper)).toEqual([
      'Open a new tab, type about:config and press Enter, then click "Accept the Risk and Continue".',
      "Search for dom.securecontext.allowlist.",
      'If it is not there, choose "String" and click "+". Put in this and click the tick: neoaprs-pi.localCopy If it has text already, add a comma and this at the end.',
      "Come back here and Reload",
    ]);
  });

  it("gives Chrome the flags address and the origin of the page, with the port", () => {
    const wrapper = panel(CHROME, "192.168.1.20");
    expect(wrapper.find("h4").text()).toBe("Enable pop-ups in Chrome");
    expect(wrapper.findAll(".copyfield code").map((c) => c.text())).toEqual([
      "chrome://flags/#unsafely-treat-insecure-origin-as-secure",
      "http://192.168.1.20:7303",
    ]);
    expect(steps(wrapper)).toHaveLength(4);
    expect(steps(wrapper)[2]).toBe('Click "Relaunch" at the bottom.');
  });

  it("uses the flags address of Edge, Opera and Brave", () => {
    const flag = (wrapper: ReturnType<typeof panel>) => wrapper.find(".copyfield code").text();
    expect(flag(panel(EDGE))).toBe("edge://flags/#unsafely-treat-insecure-origin-as-secure");
    expect(flag(panel(OPERA))).toBe("opera://flags/#unsafely-treat-insecure-origin-as-secure");
    const brave = panel(CHROME, "neoaprs-pi.local", { brave: {} });
    expect(brave.find("h4").text()).toBe("Enable pop-ups in Brave");
    expect(flag(brave)).toBe("brave://flags/#unsafely-treat-insecure-origin-as-secure");
  });

  it("says plainly on a phone that it needs https and that the sound and the tab alert are used", () => {
    for (const userAgent of [ANDROID_CHROME, IPHONE]) {
      const wrapper = panel(userAgent);
      expect(wrapper.find("ol").exists()).toBe(false);
      expect(wrapper.find(".copyfield").exists()).toBe(false);
      expect(wrapper.text()).toContain("Phones show pop-ups only for https pages");
      expect(wrapper.text()).toContain("sound and the tab alert work");
    }
  });

  it("has no steps for a browser that cannot allow them", () => {
    const wrapper = panel(SAFARI);
    expect(wrapper.find("ol").exists()).toBe(false);
    expect(wrapper.text()).toContain("no way to allow pop-ups for this address");
  });

  it("copies the host alone for Firefox, whatever the port", async () => {
    const wrapper = panel(FIREFOX_WINDOWS, "192.168.1.20");
    await copyButton(wrapper, 0)?.trigger("click");
    await flushPromises();
    expect(writeText).toHaveBeenCalledExactlyOnceWith("192.168.1.20");
    expect(copyButton(wrapper, 0)?.text()).toBe("Copied");
  });

  it("copies the flags address and the origin for Chrome", async () => {
    const wrapper = panel(CHROME, "neoaprs-pi.local");
    await copyButton(wrapper, 0)?.trigger("click");
    await copyButton(wrapper, 1)?.trigger("click");
    await flushPromises();
    expect(writeText.mock.calls).toEqual([["chrome://flags/#unsafely-treat-insecure-origin-as-secure"], ["http://neoaprs-pi.local:7303"]]);
  });

  it("reloads the page from Reload", async () => {
    const reload = vi.spyOn(window.location, "reload").mockImplementation(() => undefined);
    const wrapper = panel(FIREFOX_WINDOWS);
    await wrapper.findAll("ol button").at(-1)?.trigger("click");
    expect(reload).toHaveBeenCalledOnce();
  });

  it("closes from the cross", async () => {
    const wrapper = panel(CHROME);
    await wrapper.find("header button").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("has the two flatpak commands, to copy, in a fold for Firefox on Linux only", async () => {
    const wrapper = panel(FIREFOX_LINUX);
    const fold = wrapper.find("details");
    expect(fold.find("summary").text()).toBe("If the pop-up still doesn't show");
    expect(fold.findAll("code").map((c) => c.text())).toEqual([
      "flatpak override --user --talk-name=org.freedesktop.Notifications org.mozilla.firefox",
      "flatpak override --user --env=NOTIFY_IGNORE_PORTAL=1 org.mozilla.firefox",
    ]);
    await fold.findAll("button")[1]?.trigger("click");
    await flushPromises();
    expect(writeText).toHaveBeenCalledExactlyOnceWith("flatpak override --user --env=NOTIFY_IGNORE_PORTAL=1 org.mozilla.firefox");
    expect(panel(FIREFOX_WINDOWS).find("details").exists()).toBe(false);
    expect(panel(CHROME).find("details").exists()).toBe(false);
  });
});
