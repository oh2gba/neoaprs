import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import UpdatePanel from "@/components/UpdatePanel.vue";
import type { InstallInfo } from "@/protocol/protocol";

afterEach(() => vi.restoreAllMocks());

const install = (kind: InstallInfo["kind"], extra: Partial<InstallInfo> = {}): InstallInfo => ({ kind, appimage: "", service: false, arch: "", ...extra });
const panel = (info: InstallInfo | null, version = "0.4.0") => mount(UpdatePanel, { props: { version, install: info } });
const copyButtons = (wrapper: ReturnType<typeof panel>) => wrapper.findAll("button").filter((b) => b.text().startsWith("Copy") || b.text() === "Copied");

describe("UpdatePanel", () => {
  it("is headed Update to the version, with a link to the notes of that release and what stays", () => {
    const wrapper = panel(install("uv-tool"));
    expect(wrapper.find("h2").text()).toBe("Update to 0.4.0");
    const news = wrapper.find(".updatepanel-news a");
    expect(news.text()).toBe("What is new");
    expect(news.attributes("href")).toBe("https://github.com/oh2gba/neoaprs/releases/tag/v0.4.0");
    expect(news.attributes("rel")).toContain("noopener");
    expect(wrapper.find(".updatepanel-news").text()).toBe("What is new");
    expect(wrapper.text()).toContain("Your data (settings, messages, packets, the map) stays.");
    expect(wrapper.text()).toContain("Open pages load the new version by themselves after the update.");
  });

  it("gives the Windows installer as a download of the version", () => {
    const wrapper = panel(install("windows-installer"));
    const file = wrapper.find("a.updatepanel-file");
    expect(file.attributes("href")).toBe("https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/NeoAPRS-Setup-0.4.0.exe");
    expect(copyButtons(wrapper)).toHaveLength(0);
    expect(wrapper.text()).not.toContain("this copy");
  });

  it("gives an AppImage its download, its commands and, with a service, the service install of the new file", () => {
    const wrapper = panel(install("appimage", { appimage: "/home/ham/NeoAPRS-0.3.0-x86_64.AppImage", service: true }));
    expect(wrapper.find("a.updatepanel-file").attributes("href")).toBe(
      "https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/NeoAPRS-0.4.0-x86_64.AppImage",
    );
    expect(wrapper.findAll("code").map((c) => c.text())).toEqual([
      "chmod +x NeoAPRS-0.4.0-x86_64.AppImage",
      "./NeoAPRS-0.4.0-x86_64.AppImage",
      "./NeoAPRS-0.4.0-x86_64.AppImage service install",
    ]);
    expect(wrapper.text()).toContain("Delete the old file, NeoAPRS-0.3.0-x86_64.AppImage");
    expect(panel(install("appimage")).findAll("code")).toHaveLength(2);
  });

  it("gives a deb its download for the architecture, the apt command and, with a service, the restart", () => {
    const wrapper = panel(install("deb", { arch: "arm64", service: true }));
    expect(wrapper.find("a[href$='neoaprs_0.4.0_arm64.deb']").exists()).toBe(true);
    expect(wrapper.findAll("code").map((c) => c.text())).toEqual(["sudo apt install ./neoaprs_0.4.0_arm64.deb", "systemctl --user restart neoaprs"]);
  });

  it("gives the install line of the uv tool, pip's commands and a clone's, each with a copy button", () => {
    expect(panel(install("uv-tool")).find("code").text()).toBe("curl -LsSf https://github.com/oh2gba/neoaprs/releases/latest/download/install.sh | sh");
    const pip = panel(install("pip", { service: true }));
    expect(pip.findAll("code").map((c) => c.text())).toEqual(["pip install -U neoaprs", "uv pip install -U neoaprs", "neoaprs service install"]);
    expect(copyButtons(pip)).toHaveLength(3);
    const clone = panel(install("source", { service: true }));
    expect(clone.findAll("code").map((c) => c.text())).toEqual(["git pull", "uv sync", "systemctl --user restart neoaprs"]);
  });

  it("copies the command of a button to the clipboard and says Copied for a moment", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    const wrapper = panel(install("source", { service: true }));
    const buttons = copyButtons(wrapper);
    await buttons[1]?.trigger("click");
    await vi.advanceTimersByTimeAsync(0);
    expect(writeText).toHaveBeenCalledExactlyOnceWith("uv sync");
    expect(copyButtons(wrapper).map((b) => b.text())).toEqual(["Copy", "Copied", "Copy"]);
    await vi.advanceTimersByTimeAsync(2000);
    expect(copyButtons(wrapper).map((b) => b.text())).toEqual(["Copy", "Copy", "Copy"]);
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("copies through a text field where the page has no clipboard of its own", async () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: undefined });
    const exec = vi.fn(() => true);
    Object.defineProperty(document, "execCommand", { value: exec, configurable: true });
    const wrapper = panel(install("pip"));
    await copyButtons(wrapper)[0]?.trigger("click");
    await vi.waitFor(() => expect(exec).toHaveBeenCalledWith("copy"));
    expect(document.querySelector("textarea")).toBeNull();
    await vi.waitFor(() => expect(copyButtons(wrapper)[0]?.text()).toBe("Copied"));
    vi.unstubAllGlobals();
  });

  it("says Not copied when the copy is refused", async () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: undefined });
    Object.defineProperty(document, "execCommand", { value: () => false, configurable: true });
    const wrapper = panel(install("pip"));
    await copyButtons(wrapper)[0]?.trigger("click");
    await vi.waitFor(() => expect(wrapper.text()).toContain("Not copied"));
    vi.unstubAllGlobals();
  });

  it("has only the release page while the install kind is not known", () => {
    const wrapper = panel(null);
    expect(wrapper.find("a.updatepanel-file").attributes("href")).toBe("https://github.com/oh2gba/neoaprs/releases/tag/v0.4.0");
    expect(wrapper.find("code").exists()).toBe(false);
  });

  it("closes with the cross and with Escape", async () => {
    const wrapper = mount(UpdatePanel, { props: { version: "0.4.0", install: install("pip") }, attachTo: document.body });
    expect(wrapper.find("button[aria-label=Close]").classes()).toContain("xbtn");
    await wrapper.find("button[aria-label=Close]").trigger("click");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(wrapper.emitted("close")).toHaveLength(2);
    wrapper.unmount();
  });
});
