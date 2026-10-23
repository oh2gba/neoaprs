import { describe, expect, it } from "vitest";
import { appImageUrl, debName, debUrl, installerUrl, INSTALL_LINE, releaseNotes, updateHelp } from "@/lib/update";
import type { InstallInfo } from "@/protocol/protocol";

const install = (kind: InstallInfo["kind"], extra: Partial<InstallInfo> = {}): InstallInfo => ({ kind, appimage: "", service: false, arch: "", ...extra });
const commands = (help: ReturnType<typeof updateHelp>) => help.steps.flatMap((s) => (s.command ? [s.command] : []));

describe("the addresses", () => {
  it("are built from the version", () => {
    expect(releaseNotes("0.4.0")).toBe("https://github.com/oh2gba/neoaprs/releases/tag/v0.4.0");
    expect(installerUrl("0.4.0")).toBe("https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/NeoAPRS-Setup-0.4.0.exe");
    expect(appImageUrl("0.4.0")).toBe("https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/NeoAPRS-0.4.0-x86_64.AppImage");
    expect(debName("0.4.0", "arm64")).toBe("neoaprs_0.4.0_arm64.deb");
    expect(debUrl("0.4.0", "amd64")).toBe("https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/neoaprs_0.4.0_amd64.deb");
  });
});

describe("updateHelp", () => {
  it("is a download and a run for the Windows installer", () => {
    const help = updateHelp(install("windows-installer"), "0.4.0");
    expect(help.steps.map((s) => s.link?.href)).toEqual([installerUrl("0.4.0"), undefined]);
    expect(help.steps[0]?.link?.label).toBe("NeoAPRS-Setup-0.4.0.exe");
    expect(commands(help)).toEqual([]);
  });

  it("is a download, chmod and a start for an AppImage, with the old file named to delete", () => {
    const help = updateHelp(install("appimage", { appimage: "/home/ham/Apps/NeoAPRS-0.3.0-x86_64.AppImage" }), "0.4.0");
    expect(help.steps[0]?.link?.href).toBe(appImageUrl("0.4.0"));
    expect(commands(help)).toEqual(["chmod +x NeoAPRS-0.4.0-x86_64.AppImage", "./NeoAPRS-0.4.0-x86_64.AppImage"]);
    expect(help.steps.at(-1)?.text).toBe("Delete the old file, NeoAPRS-0.3.0-x86_64.AppImage");
  });

  it("adds service install of the new file when a service runs the AppImage", () => {
    const help = updateHelp(install("appimage", { appimage: "/home/ham/NeoAPRS.AppImage", service: true }), "0.4.0");
    expect(commands(help)).toEqual([
      "chmod +x NeoAPRS-0.4.0-x86_64.AppImage",
      "./NeoAPRS-0.4.0-x86_64.AppImage",
      "./NeoAPRS-0.4.0-x86_64.AppImage service install",
    ]);
  });

  it("is the package of the machine's architecture, apt install and a restart of the service for a deb", () => {
    const help = updateHelp(install("deb", { arch: "arm64", service: true }), "0.4.0");
    expect(help.steps[0]?.link).toEqual({
      href: "https://github.com/oh2gba/neoaprs/releases/download/v0.4.0/neoaprs_0.4.0_arm64.deb",
      label: "neoaprs_0.4.0_arm64.deb",
    });
    expect(commands(help)).toEqual(["sudo apt install ./neoaprs_0.4.0_arm64.deb", "systemctl --user restart neoaprs"]);
    expect(updateHelp(install("deb", { arch: "amd64" }), "0.5.1").steps[0]?.link?.href).toContain("/v0.5.1/neoaprs_0.5.1_amd64.deb");
    const by_hand = updateHelp(install("deb", { arch: "amd64" }), "0.4.0");
    expect(commands(by_hand)).toEqual(["sudo apt install ./neoaprs_0.4.0_amd64.deb"]);
    expect(by_hand.steps.at(-1)?.text).toBe("Quit NeoAPRS and start it again");
  });

  it("sends a deb of a machine without a package to the release page and installs whichever file was downloaded", () => {
    const help = updateHelp(install("deb"), "0.4.0");
    expect(help.steps[0]?.link?.href).toBe(releaseNotes("0.4.0"));
    expect(commands(help)).toEqual(["sudo apt install ./neoaprs_0.4.0_*.deb"]);
  });

  it("is the install line again for the uv tool", () => {
    expect(commands(updateHelp(install("uv-tool", { service: true }), "0.4.0"))).toEqual([INSTALL_LINE]);
    expect(INSTALL_LINE).toBe("curl -LsSf https://github.com/oh2gba/neoaprs/releases/latest/download/install.sh | sh");
  });

  it("is pip or uv pip, then a restart of the service or of the program, for a plain environment", () => {
    expect(commands(updateHelp(install("pip", { service: true }), "0.4.0"))).toEqual([
      "pip install -U neoaprs",
      "uv pip install -U neoaprs",
      "neoaprs service install",
    ]);
    const by_hand = updateHelp(install("pip"), "0.4.0");
    expect(commands(by_hand)).toEqual(["pip install -U neoaprs", "uv pip install -U neoaprs"]);
    expect(by_hand.steps.at(-1)?.text).toBe("Quit NeoAPRS and start it again");
  });

  it("is a pull, a sync and a restart for a clone", () => {
    expect(commands(updateHelp(install("source", { service: true }), "0.4.0"))).toEqual(["git pull", "uv sync", "systemctl --user restart neoaprs"]);
    expect(commands(updateHelp(install("source"), "0.4.0"))).toEqual(["git pull", "uv sync"]);
  });

  it("has only the release page while the daemon has not said how it was installed", () => {
    const help = updateHelp(null, "0.4.0");
    expect(help.steps).toHaveLength(1);
    expect(help.steps[0]?.link?.href).toBe(releaseNotes("0.4.0"));
  });
});
