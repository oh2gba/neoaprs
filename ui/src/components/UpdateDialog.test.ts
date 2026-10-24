import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import UpdateDialog from "@/components/UpdateDialog.vue";
import type { InstallInfo, UpdateState } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { status } from "@/test/fixtures";

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

const install = (kind: InstallInfo["kind"], extra: Partial<InstallInfo> = {}): InstallInfo => ({ kind, appimage: "", service: false, arch: "", ...extra });
const job = (over: Partial<UpdateState> = {}): UpdateState => ({
  supported: true,
  state: "idle",
  version: "",
  percent: null,
  downloaded: 0,
  total: null,
  problem: "",
  detail: "",
  ...over,
});
const dialog = (given: Given = {}, version = "0.4.0") => {
  const daemon = fakeDaemon({ install: install("pip"), version: "0.3.0", ...given });
  const wrapper = mount(UpdateDialog, { props: { version }, global: withDaemon(daemon), attachTo: document.body });
  return { wrapper, daemon };
};
const copyButtons = (wrapper: ReturnType<typeof dialog>["wrapper"]) =>
  wrapper.findAll("button").filter((b) => b.text().startsWith("Copy") || b.text() === "Copied");

describe("UpdateDialog", () => {
  it("is a modal dialog headed with the new version, the installed one small, and what is new", () => {
    const { wrapper } = dialog({ status: status({ update: { version: "0.4.0", url: "", message: "Fixes the map download" } }) });
    const box = wrapper.find("[role=dialog]");
    expect(box.attributes("aria-modal")).toBe("true");
    expect(box.attributes("aria-labelledby")).toBe("updatedialog-title");
    expect(wrapper.find("#updatedialog-title").text()).toBe("NeoAPRS 0.4.0 is available");
    expect(wrapper.find(".updatedialog-installed").text()).toBe("You have NeoAPRS 0.3.0");
    expect(wrapper.find(".updatedialog-news h3").text()).toBe("What's new");
    expect(wrapper.find(".updatedialog-news p").text()).toBe("Fixes the map download");
    const news = wrapper.find(".updatedialog-news a.btn");
    expect(news.text()).toBe("What's new in 0.4.0");
    expect(news.attributes("href")).toBe("https://github.com/oh2gba/neoaprs/releases/tag/v0.4.0");
    expect(news.attributes("rel")).toContain("noopener");
    expect(wrapper.text()).toContain("Your settings, messages and map stay. Open pages reload by themselves.");
    expect(wrapper.find(".updatedialog-backdrop").exists()).toBe(true);
  });

  it("has no note when the version page sent none", () => {
    expect(dialog().wrapper.find(".updatedialog-news p").exists()).toBe(false);
  });

  it("moves the focus into itself: onto Update now where there is one, else onto the dialog", async () => {
    const { wrapper } = dialog({ install: install("appimage"), selfUpdate: job() });
    await vi.waitFor(() => expect(document.activeElement).toBe(wrapper.find(".updatedialog-go").element));
    wrapper.unmount();
    const plain = dialog().wrapper;
    await vi.waitFor(() => expect(document.activeElement).toBe(plain.find("[role=dialog]").element));
  });

  it("gives the focus back to what had it when it closes", async () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const { wrapper } = dialog();
    await vi.waitFor(() => expect(document.activeElement).not.toBe(opener));
    wrapper.unmount();
    expect(document.activeElement).toBe(opener);
  });

  it("keeps Tab and Shift+Tab inside", () => {
    const { wrapper } = dialog({ install: install("source") });
    const items = wrapper.findAll("a[href], button");
    const first = items[0]?.element as HTMLElement;
    const last = items.at(-1)?.element as HTMLElement;
    last.focus();
    const forward = new KeyboardEvent("keydown", { key: "Tab", cancelable: true });
    document.dispatchEvent(forward);
    expect(forward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);
    const back = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, cancelable: true });
    document.dispatchEvent(back);
    expect(document.activeElement).toBe(last);
  });

  it("closes with the cross, with Escape and with a press beside it, not with one inside", async () => {
    const { wrapper } = dialog();
    expect(wrapper.find("button[aria-label=Close]").classes()).toContain("xbtn");
    await wrapper.find("button[aria-label=Close]").trigger("click");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await wrapper.find(".updatedialog-backdrop").trigger("pointerdown");
    await wrapper.find(".updatedialog").trigger("pointerdown");
    await wrapper.find(".updatedialog h2").trigger("pointerdown");
    expect(wrapper.emitted("close")).toHaveLength(3);
  });

  it("offers Update now where the daemon can update itself, with the steps by hand folded under it", async () => {
    const { wrapper, daemon } = dialog({ install: install("windows-installer"), selfUpdate: job() });
    const go = wrapper.find("button.updatedialog-go");
    expect(go.text()).toBe("Update now");
    expect(go.classes()).toContain("primary");
    const hand = wrapper.find("details.updatedialog-hand");
    expect(hand.find("summary").text()).toBe("Or update by hand");
    expect(hand.attributes("open")).toBeUndefined();
    expect(hand.find("a.updatesteps-file").attributes("href")).toBe("https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/NeoAPRS-Setup-0.4.0.exe");
    await go.trigger("click");
    expect(daemon.send).toHaveBeenCalledExactlyOnceWith({ cmd: "update_now", version: "0.4.0" });
  });

  it("has no Update now where the daemon cannot update itself, and the steps are the dialog's", () => {
    for (const given of [
      { install: install("deb", { arch: "arm64" }), selfUpdate: job({ supported: false }) },
      { install: install("appimage"), selfUpdate: null },
    ]) {
      const { wrapper } = dialog(given);
      expect(wrapper.find(".updatedialog-go").exists()).toBe(false);
      expect(wrapper.find(".updatedialog-now").exists()).toBe(false);
      expect(wrapper.find("details").exists()).toBe(false);
      expect(wrapper.find("section.updatedialog-hand h3").text()).toBe("How to update");
      wrapper.unmount();
    }
  });

  it("shows the download with its percent and a Cancel, then each step, and the restart", async () => {
    const { wrapper, daemon } = dialog({
      install: install("windows-installer"),
      selfUpdate: job({ state: "downloading", version: "0.4.0", percent: 42, downloaded: 42, total: 100 }),
    });
    expect(wrapper.find(".updatedialog-progress").text()).toBe("Downloading… 42 %");
    expect(wrapper.find(".updatedialog-progress").attributes("role")).toBe("status");
    expect((wrapper.find("progress").element as HTMLProgressElement).value).toBe(42);
    expect(wrapper.find(".updatedialog-go").exists()).toBe(false);
    const cancel = wrapper.findAll(".updatedialog-now button").find((b) => b.text() === "Cancel");
    await cancel?.trigger("click");
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "update_cancel" });
    await tell(daemon, { selfUpdate: job({ state: "verifying", version: "0.4.0" }) });
    expect(wrapper.find(".updatedialog-progress").text()).toBe("Checking the download…");
    expect(wrapper.find("progress").exists()).toBe(false);
    await tell(daemon, { selfUpdate: job({ state: "installing", version: "0.4.0" }) });
    expect(wrapper.find(".updatedialog-progress").text()).toBe("Installing…");
    expect(wrapper.findAll(".updatedialog-now button")).toHaveLength(0);
    await tell(daemon, { selfUpdate: job({ state: "restarting", version: "0.4.0" }) });
    expect(wrapper.find(".updatedialog-progress").text()).toBe("Installing… NeoAPRS restarts in a moment");
    await tell(daemon, { connection: "closed" });
    expect(wrapper.find(".updatedialog-progress").text()).toBe("NeoAPRS is restarting. This page reconnects by itself.");
  });

  it("keeps the progress while the topic says the copy can no longer update itself (the restart is on its way)", () => {
    const { wrapper } = dialog({ install: install("appimage"), selfUpdate: job({ supported: false, state: "restarting", version: "0.4.0" }) });
    expect(wrapper.find(".updatedialog-progress").text()).toBe("NeoAPRS restarts in a moment");
  });

  it("says a failure in plain words, with the detail as its title, offers Try again and opens the steps by hand", async () => {
    const detail = "NeoAPRS-0.4.0-x86_64.AppImage is not the file of the release: its SHA-256 is ab, SHA256SUMS says cd";
    const { wrapper, daemon } = dialog({ install: install("appimage"), selfUpdate: job({ state: "error", version: "0.4.0", problem: "checksum", detail }) });
    const problem = wrapper.find(".updatedialog-problem");
    expect(problem.text()).toBe("The download is not the release's file, so it was deleted and nothing was installed. Try again.");
    expect(problem.attributes("role")).toBe("alert");
    expect(problem.attributes("title")).toBe(detail);
    expect(wrapper.find("details.updatedialog-hand").attributes("open")).toBeDefined();
    await wrapper.find(".updatedialog-go").trigger("click");
    expect(wrapper.find(".updatedialog-go").text()).toBe("Try again");
    expect(daemon.send).toHaveBeenCalledWith({ cmd: "update_now", version: "0.4.0" });
  });

  it("draws the steps for each way of install: files as buttons, commands with Copy", () => {
    const win = dialog({ install: install("windows-installer"), selfUpdate: job({ supported: false }) }).wrapper;
    expect(win.find("a.updatesteps-file").classes()).toContain("btn");
    expect(copyButtons(win)).toHaveLength(0);
    win.unmount();
    const image = dialog({ install: install("appimage", { appimage: "/home/ham/NeoAPRS-0.3.0-x86_64.AppImage", service: true }) }).wrapper;
    expect(image.findAll("code").map((c) => c.text())).toEqual([
      "chmod +x NeoAPRS-0.4.0-x86_64.AppImage",
      "./NeoAPRS-0.4.0-x86_64.AppImage",
      "./NeoAPRS-0.4.0-x86_64.AppImage service install",
    ]);
    expect(image.text()).toContain("Then delete the old file, NeoAPRS-0.3.0-x86_64.AppImage");
    image.unmount();
    const deb = dialog({ install: install("deb", { arch: "arm64", service: true }) }).wrapper;
    expect(deb.find("a[href$='neoaprs_0.4.0_arm64.deb']").exists()).toBe(true);
    expect(deb.findAll("code").map((c) => c.text())).toEqual(["sudo apt install ./neoaprs_0.4.0_arm64.deb", "systemctl --user restart neoaprs"]);
    deb.unmount();
    expect(
      dialog({ install: install("uv-tool", { service: true }) })
        .wrapper.find("code")
        .text(),
    ).toContain("install.sh | sh");
    const clone = dialog({ install: install("source", { service: true }) }).wrapper;
    expect(clone.findAll("code").map((c) => c.text())).toEqual(["git pull", "uv sync", "systemctl --user restart neoaprs"]);
    expect(copyButtons(clone)).toHaveLength(3);
  });

  it("has only the release page while the install kind is not known", () => {
    const { wrapper } = dialog({ install: null });
    expect(wrapper.find("a.updatesteps-file").attributes("href")).toBe("https://github.com/oh2gba/neoaprs/releases/tag/v0.4.0");
    expect(wrapper.find("code").exists()).toBe(false);
  });

  it("copies the command of a button to the clipboard and says Copied for a moment", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    const { wrapper } = dialog({ install: install("source", { service: true }) });
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

  it("copies through a text field where the page has no clipboard of its own, and says Not copied when that is refused", async () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: undefined });
    const exec = vi.fn(() => true);
    Object.defineProperty(document, "execCommand", { value: exec, configurable: true });
    const { wrapper } = dialog({ install: install("source") });
    await copyButtons(wrapper)[0]?.trigger("click");
    await vi.waitFor(() => expect(exec).toHaveBeenCalledWith("copy"));
    await vi.waitFor(() => expect(copyButtons(wrapper)[0]?.text()).toBe("Copied"));
    Object.defineProperty(document, "execCommand", { value: () => false, configurable: true });
    await copyButtons(wrapper)[1]?.trigger("click");
    await vi.waitFor(() => expect(wrapper.text()).toContain("Not copied"));
    vi.unstubAllGlobals();
  });
});
