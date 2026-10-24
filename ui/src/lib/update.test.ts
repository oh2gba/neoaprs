import { describe, expect, it } from "vitest";
import {
  appImageUrl,
  debName,
  debUrl,
  installerUrl,
  INSTALL_LINE,
  problemText,
  progressText,
  releaseNotes,
  updateHelp,
  updateRunning,
  wheelUrl,
} from "@/lib/update";
import type { InstallInfo, UpdateState } from "@/protocol/protocol";

const install = (kind: InstallInfo["kind"], extra: Partial<InstallInfo> = {}): InstallInfo => ({ kind, appimage: "", service: false, arch: "", ...extra });
const commands = (steps: ReturnType<typeof updateHelp>) => steps.flatMap((s) => (s.command ? [s.command] : []));
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

describe("the addresses", () => {
  it("are built from the version", () => {
    expect(releaseNotes("0.4.0")).toBe("https://github.com/oh2gba/neoaprs/releases/tag/v0.4.0");
    expect(installerUrl("0.4.0")).toBe("https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/NeoAPRS-Setup-0.4.0.exe");
    expect(appImageUrl("0.4.0")).toBe("https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/NeoAPRS-0.4.0-x86_64.AppImage");
    expect(debName("0.4.0", "arm64")).toBe("neoaprs_0.4.0_arm64.deb");
    expect(debUrl("0.4.0", "amd64")).toBe("https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/neoaprs_0.4.0_amd64.deb");
    expect(wheelUrl("0.4.0")).toBe("https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/neoaprs-0.4.0-py3-none-any.whl");
  });
});

describe("updateHelp", () => {
  it("is a download, a run and the restart for the Windows installer, in plain words", () => {
    const steps = updateHelp(install("windows-installer"), "0.4.0");
    expect(steps.map((s) => s.text)).toEqual(["Download the installer", "Run it. Your settings and messages stay.", "When it is done, NeoAPRS starts again."]);
    expect(steps[0]?.link).toEqual({ href: installerUrl("0.4.0"), label: "NeoAPRS-Setup-0.4.0.exe" });
    expect(commands(steps)).toEqual([]);
  });

  it("is a download, chmod and a start for an AppImage, with the old file named to delete", () => {
    const steps = updateHelp(install("appimage", { appimage: "/home/ham/Apps/NeoAPRS-0.3.0-x86_64.AppImage" }), "0.4.0");
    expect(steps[0]?.link?.href).toBe(appImageUrl("0.4.0"));
    expect(commands(steps)).toEqual(["chmod +x NeoAPRS-0.4.0-x86_64.AppImage", "./NeoAPRS-0.4.0-x86_64.AppImage"]);
    expect(steps[2]?.text).toBe("Quit NeoAPRS and start the new file instead of the old one");
    expect(steps.at(-1)?.text).toBe("Then delete the old file, NeoAPRS-0.3.0-x86_64.AppImage");
  });

  it("adds service install of the new file when a service runs the AppImage", () => {
    const steps = updateHelp(install("appimage", { appimage: "/home/ham/NeoAPRS.AppImage", service: true }), "0.4.0");
    expect(commands(steps)).toEqual([
      "chmod +x NeoAPRS-0.4.0-x86_64.AppImage",
      "./NeoAPRS-0.4.0-x86_64.AppImage",
      "./NeoAPRS-0.4.0-x86_64.AppImage service install",
    ]);
  });

  it("is the package of the machine's architecture, one apt command and, for a service, the restart", () => {
    const steps = updateHelp(install("deb", { arch: "arm64", service: true }), "0.4.0");
    expect(steps[0]?.link).toEqual({
      href: "https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/neoaprs_0.4.0_arm64.deb",
      label: "neoaprs_0.4.0_arm64.deb",
    });
    expect(commands(steps)).toEqual(["sudo apt install ./neoaprs_0.4.0_arm64.deb", "systemctl --user restart neoaprs"]);
    expect(steps[2]?.text).toBe("The service restarts by itself. If it still shows the old version:");
    expect(updateHelp(install("deb", { arch: "amd64" }), "0.5.1")[0]?.link?.href).toContain("/v0.5.1/neoaprs_0.5.1_amd64.deb");
    const byHand = updateHelp(install("deb", { arch: "amd64" }), "0.4.0");
    expect(commands(byHand)).toEqual(["sudo apt install ./neoaprs_0.4.0_amd64.deb"]);
    expect(byHand.at(-1)?.text).toBe("Quit NeoAPRS and start it again");
  });

  it("sends a deb of a machine without a package to the release page and installs whichever file was downloaded", () => {
    const steps = updateHelp(install("deb"), "0.4.0");
    expect(steps[0]?.link?.href).toBe(releaseNotes("0.4.0"));
    expect(commands(steps)).toEqual(["sudo apt install ./neoaprs_0.4.0_*.deb"]);
  });

  it("is the install line again for the uv tool, and a restart by hand without a service", () => {
    expect(commands(updateHelp(install("uv-tool", { service: true }), "0.4.0"))).toEqual([INSTALL_LINE]);
    expect(updateHelp(install("uv-tool", { service: true }), "0.4.0")).toHaveLength(1);
    expect(updateHelp(install("uv-tool"), "0.4.0").at(-1)?.text).toBe("Quit NeoAPRS and start it again");
    expect(INSTALL_LINE).toBe("curl -LsSf https://github.com/oh2gba/neoaprs/releases/latest/download/install.sh | sh");
  });

  it("is pip with the release's wheel, then a restart of the service or of the program, for a plain environment", () => {
    expect(commands(updateHelp(install("pip", { service: true }), "0.4.0"))).toEqual([`pip install -U ${wheelUrl("0.4.0")}`, "neoaprs service install"]);
    const byHand = updateHelp(install("pip"), "0.4.0");
    expect(commands(byHand)).toEqual([`pip install -U ${wheelUrl("0.4.0")}`]);
    expect(byHand.at(-1)?.text).toBe("Quit NeoAPRS and start it again");
  });

  it("is a pull, a sync and a restart for a clone", () => {
    expect(commands(updateHelp(install("source", { service: true }), "0.4.0"))).toEqual(["git pull", "uv sync", "systemctl --user restart neoaprs"]);
    expect(commands(updateHelp(install("source"), "0.4.0"))).toEqual(["git pull", "uv sync"]);
  });

  it("names no developer's tool for the kinds of the installers and the package", () => {
    for (const kind of ["windows-installer", "appimage", "deb"] as const) {
      const words = updateHelp(install(kind, { arch: "amd64", service: true }), "0.4.0")
        .map((s) => s.text)
        .join(" ");
      expect(words).not.toMatch(/\b(git|uv|pip|venv)\b/);
    }
  });

  it("has only the release page while the daemon has not said how it was installed", () => {
    const steps = updateHelp(null, "0.4.0");
    expect(steps).toHaveLength(1);
    expect(steps[0]?.link?.href).toBe(releaseNotes("0.4.0"));
  });
});

describe("the progress of Update now", () => {
  it("says each step, the percent of the download, and the restart by the kind and the socket", () => {
    expect(progressText(job(), "appimage", true)).toBeNull();
    expect(progressText(job({ state: "downloading", percent: 42 }), "appimage", true)).toBe("Downloading… 42 %");
    expect(progressText(job({ state: "downloading", downloaded: 12_400_000 }), "appimage", true)).toBe("Downloading… 12 MB");
    expect(progressText(job({ state: "verifying" }), "appimage", true)).toBe("Checking the download…");
    expect(progressText(job({ state: "installing" }), "appimage", true)).toBe("Installing…");
    expect(progressText(job({ state: "restarting" }), "appimage", true)).toBe("NeoAPRS restarts in a moment");
    expect(progressText(job({ state: "restarting" }), "windows-installer", true)).toBe("Installing… NeoAPRS restarts in a moment");
    expect(progressText(job({ state: "restarting" }), "windows-installer", false)).toBe("NeoAPRS is restarting. This page reconnects by itself.");
    expect(progressText(job({ state: "error", problem: "checksum" }), "appimage", true)).toBeNull();
  });

  it("says each problem in plain words", () => {
    expect(problemText("")).toBe("");
    expect(problemText("checksum")).toBe("The download is not the release's file, so it was deleted and nothing was installed. Try again.");
    expect(problemText("download")).toContain("Check the internet connection");
    expect(problemText("no_restart")).toContain("Quit NeoAPRS and start it again");
  });

  it("is running from the download to the restart", () => {
    expect(
      ["idle", "downloading", "verifying", "installing", "restarting", "error"].map((state) => updateRunning(job({ state: state as UpdateState["state"] }))),
    ).toEqual([false, true, true, true, true, false]);
    expect(updateRunning(null)).toBe(false);
  });
});
