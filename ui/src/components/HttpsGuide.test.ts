// The guide to install NeoAPRS's certificate, the Web page group's part of it (switch, (i), link, problem) and the pop-up guide's first step while the daemon serves https.
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import HttpsGuide from "@/components/HttpsGuide.vue";
import PopupHelp from "@/components/PopupHelp.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import type { HttpsState } from "@/protocol/protocol";
import { openedAt, resetSeen } from "@/test/fakealert";
import { configValues } from "@/test/fixtures";

const FINGERPRINT = "AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89:AB:CD:EF:01:23:45:67:89";
const ON: HttpsState = { on: true, port: 7304, fingerprint: FINGERPRINT, problem: "" };
const OFF: HttpsState = { on: false, port: 0, fingerprint: "", problem: "" };
const NETWORK = { "web/network": "true", "web/key": "k7m2-x9pq-4hrt" };

const ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36";
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";
const MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15";
const LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";
const FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0";

function guide(userAgent: string, https: HttpsState = ON, props: Record<string, unknown> = {}) {
  vi.stubGlobal("navigator", { userAgent, maxTouchPoints: 0 });
  openedAt("192.168.1.20");
  return mount(HttpsGuide, { props: { https, ...props } });
}

const steps = (wrapper: ReturnType<typeof guide>) => wrapper.findAll("ol li").map((li) => li.text());

afterEach(() => {
  vi.unstubAllGlobals();
  resetSeen();
});

describe("the guide", () => {
  it("has a download of the certificate under its name, the fingerprint to compare, and the line about continuing past the warning", () => {
    const wrapper = guide(LINUX);
    const download = wrapper.find("a.btn");
    expect(download.text()).toBe("Download certificate");
    expect(download.attributes("href")).toBe("/neoaprs-ca.crt");
    expect(download.attributes("download")).toBe("NeoAPRS-CA.crt");
    expect(wrapper.find(".copyfield code").text()).toBe(FINGERPRINT);
    expect(wrapper.find(".httpsguide-print").text()).toContain("Fingerprint");
    const line = wrapper.find("p");
    expect(line.text()).toBe("Or just open the secure page and continue past the warning.");
    expect(line.find("a").attributes("href")).toBe("https://192.168.1.20:7304/");
  });

  it("gives the steps of Android", () => {
    const wrapper = guide(ANDROID);
    expect(wrapper.find("select").element.value).toBe("android");
    expect(steps(wrapper)[0]).toContain("Security → Encryption & credentials → Install a certificate → CA certificate");
  });

  it("gives the steps of an iPhone: Safari, Profile Downloaded, then Certificate Trust Settings", () => {
    const wrapper = guide(IPHONE);
    expect(wrapper.find("select").element.value).toBe("ios");
    const text = steps(wrapper).join(" ");
    expect(text).toContain("Safari");
    expect(text).toContain("Profile Downloaded → Install");
    expect(text).toContain("General → About → Certificate Trust Settings");
    expect(text).toContain("NeoAPRS local CA");
  });

  it("gives the steps of Windows, macOS, Linux Chrome and Firefox", () => {
    expect(steps(guide(WINDOWS)).join(" ")).toContain("Trusted Root Certification Authorities");
    expect(steps(guide(MAC)).join(" ")).toMatch(/Keychain Access.*System.*Always Trust/);
    expect(steps(guide(LINUX)).join(" ")).toMatch(/Manage certificates → Authorities.*Import/);
    const firefox = guide(FIREFOX);
    expect(firefox.find("select").element.value).toBe("firefox");
    expect(steps(firefox).join(" ")).toMatch(/View Certificates → Authorities.*Trust this CA to identify websites/);
  });

  it("lets the person ask for the steps of another device", async () => {
    const wrapper = guide(LINUX);
    expect(wrapper.findAll("option").map((o) => o.text())).toEqual(["Android", "iPhone, iPad", "Windows", "macOS", "Linux (Chrome)", "Firefox"]);
    await wrapper.find("select").setValue("windows");
    expect(steps(wrapper).join(" ")).toContain("Install Certificate");
  });

  it("leaves out the line about the warning on the secure page itself and where the caller has the link above", () => {
    expect(guide(LINUX, ON, { link: false }).find("p").exists()).toBe(false);
    vi.stubGlobal("navigator", { userAgent: LINUX, maxTouchPoints: 0 });
    (window as unknown as { happyDOM: { setURL(url: string): void } }).happyDOM.setURL("https://192.168.1.20:7304/");
    expect(
      mount(HttpsGuide, { props: { https: ON } })
        .find("p")
        .exists(),
    ).toBe(false);
  });
});

describe("the Web page group", () => {
  function settings(https: HttpsState, values: Record<string, string> = NETWORK) {
    const config = configValues(values);
    config.https = https;
    return mount(SettingsForm, { props: { config, lastError: null, send: vi.fn(() => true) } });
  }

  it("has one switch, Secure connection (https), with the (i), where the network is on and not before", async () => {
    const wrapper = settings(OFF);
    expect(wrapper.find("label[for='set-web-https']").text()).toBe("Secure connection (https)");
    const box = wrapper.find<HTMLInputElement>("#set-web-https");
    expect(box.attributes("type")).toBe("checkbox");
    expect(box.element.checked).toBe(false);
    await wrapper.find("button[aria-label='About the secure connection']").trigger("click");
    expect(wrapper.find(".info-text").text()).toBe(
      "Needed for pop-ups on phones and for installing NeoAPRS as an app. Browsers show a warning the first time; you can continue past it, or install NeoAPRS's certificate on each device to make the warning go away.",
    );
    expect(settings(OFF, {}).find("#set-web-https").exists()).toBe(false);
  });

  it("applies the switch at once, like any setting", async () => {
    const send = vi.fn(() => true);
    const config = configValues(NETWORK);
    const wrapper = mount(SettingsForm, { props: { config, lastError: null, send } });
    await wrapper.find("#set-web-https").setValue(true);
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "web/https": "true" } });
  });

  it("shows no guide while https is not served, and the reason when it could not start", () => {
    const off = settings(OFF);
    expect(off.find(".disclosure").exists()).toBe(false);
    expect(off.find(".httpsguide").exists()).toBe(false);
    const failed = settings({ ...OFF, problem: "the secure page cannot listen on a port after 7303: address in use" });
    expect(failed.find(".field-error").text()).toContain("address in use");
  });

  it("has the guide under a heading while https is served", () => {
    vi.stubGlobal("navigator", { userAgent: ANDROID, maxTouchPoints: 0 });
    const wrapper = settings(ON, { ...NETWORK, "web/https": "true" });
    const box = wrapper.find("details.disclosure");
    expect(box.find("summary").text()).toBe("Install the certificate on a device");
    expect(box.attributes("open")).toBeUndefined();
    expect(box.find(".httpsguide a.btn").attributes("href")).toBe("/neoaprs-ca.crt");
    expect(box.find(".httpsguide .copyfield code").text()).toBe(FINGERPRINT);
  });
});

describe("the pop-up guide", () => {
  function popup(https: HttpsState | null, userAgent = FIREFOX) {
    vi.stubGlobal("navigator", { userAgent, clipboard: { writeText: vi.fn(() => Promise.resolve()) } });
    openedAt("192.168.1.20");
    return mount(PopupHelp, { props: { https } });
  }

  it("starts with the secure page while https is served, then the certificate, and keeps the steps of http for whoever keeps it", () => {
    const wrapper = popup(ON);
    const first = wrapper.find("ol li");
    expect(first.text()).toBe("Open the secure page: https://192.168.1.20:7304/");
    expect(first.find("a").attributes("href")).toBe("https://192.168.1.20:7304/");
    expect(wrapper.find(".disclosure summary").text()).toBe("Remove the browser's warning");
    expect(wrapper.find(".httpsguide a.btn").text()).toBe("Download certificate");
    expect(wrapper.findAll(".httpsguide p")).toHaveLength(0);
    const http = wrapper.find("details.popuphelp-http");
    expect(http.find("summary").text()).toBe("Or keep http");
    expect(http.text()).toContain("dom.securecontext.allowlist");
  });

  it("is the steps of http alone while https is not served", () => {
    for (const https of [null, OFF]) {
      const wrapper = popup(https);
      expect(wrapper.find(".httpsguide").exists()).toBe(false);
      expect(wrapper.find("details.popuphelp-http").exists()).toBe(false);
      expect(wrapper.find("ol li").text()).toContain("about:config");
    }
  });
});
