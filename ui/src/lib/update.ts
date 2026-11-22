// What to do to update, for the way this copy was installed (the daemon says: `install` of its
// hello). The steps are data that the dialog (components/UpdateDialog.vue, UpdateSteps.vue) only
// draws: words, a command to copy, a file to download. Developer tools (git, uv) appear only for a
// clone of the repository; a wheel install (`uv-tool`, `pip`) is sent to the release page, where
// the supported installs are.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { InstallInfo, UpdateState } from "@/protocol/protocol";

const RELEASES = "https://github.com/oh2gba/neoaprs/releases";

export interface Step {
  text: string;
  /** A command to run, with a button that copies it. */
  command?: string;
  /** A file to download, or a page to open: a button. */
  link?: { href: string; label: string };
}

export const releaseNotes = (version: string): string => `${RELEASES}/tag/v${version}`;
const download = (version: string, name: string): string => `${RELEASES}/download/v${version}/${name}`;
const installerName = (version: string): string => `NeoAPRS-Setup-${version}.exe`;
export const installerUrl = (version: string): string => download(version, installerName(version));
const appImageName = (version: string): string => `NeoAPRS-${version}-x86_64.AppImage`;
export const appImageUrl = (version: string): string => download(version, appImageName(version));
export const debName = (version: string, arch: string): string => `neoaprs_${version}_${arch}.deb`;
export const debUrl = (version: string, arch: string): string => download(version, debName(version, arch));
const dmgName = (version: string): string => `NeoAPRS-${version}-arm64.dmg`;
export const dmgUrl = (version: string): string => download(version, dmgName(version));
/** The last part of a path of either kind. */
function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

/**
 * Quits and starts again: a service is restarted with `command`, a program started by hand is quit
 * and started.
 */
function restart(service: boolean, command: string): Step {
  return service ? { text: t("help.update.restart_service"), command } : { text: t("help.update.restart") };
}

function windowsSteps(version: string): Step[] {
  return [
    { text: t("help.update.win.download"), link: { href: installerUrl(version), label: installerName(version) } },
    { text: t("help.update.win.run") },
    { text: t("help.update.win.restart") },
  ];
}

function appImageSteps(install: InstallInfo, version: string): Step[] {
  const name = appImageName(version);
  const steps: Step[] = [
    { text: t("help.update.appimage.download"), link: { href: appImageUrl(version), label: name } },
    { text: t("help.update.appimage.executable"), command: `chmod +x ${name}` },
    { text: t("help.update.appimage.start"), command: `./${name}` },
  ];
  if (install.service) steps.push({ text: t("help.update.appimage.service"), command: `./${name} service install` });
  if (install.appimage)
    steps.push({ text: t("help.update.appimage.delete_old", { name: fileName(install.appimage) }) });
  return steps;
}

function debSteps(install: InstallInfo, version: string): Step[] {
  // The architecture is known for amd64 and arm64; for any other the release page lists the files.
  const file = install.arch ? debName(version, install.arch) : `neoaprs_${version}_*.deb`;
  return [
    install.arch
      ? { text: t("help.update.deb.download"), link: { href: debUrl(version, install.arch), label: file } }
      : {
          text: t("help.update.deb.download_here"),
          link: { href: releaseNotes(version), label: `NeoAPRS ${version}` },
        },
    { text: t("help.update.deb.install"), command: `sudo apt install ./${file}` },
    install.service
      ? { text: t("help.update.deb.service"), command: "systemctl --user restart neoaprs" }
      : { text: t("help.update.restart") },
  ];
}

function macSteps(install: InstallInfo, version: string): Step[] {
  // The app is built for Apple silicon; another Mac is sent to the release page.
  return [
    install.arch === "arm64"
      ? { text: t("help.update.macos.download"), link: { href: dmgUrl(version), label: dmgName(version) } }
      : { text: t("help.update.release_page"), link: { href: releaseNotes(version), label: `NeoAPRS ${version}` } },
    { text: t("help.update.macos.replace") },
    install.service
      ? { text: t("help.update.restart_service"), command: "launchctl kickstart -k gui/$UID/eu.oh2gba.neoaprs" }
      : { text: t("help.update.macos.start") },
  ];
}

/**
 * The steps to version `version` for a copy installed as `install`; null while the install is
 * unknown (only the release page then).
 */
export function updateHelp(install: InstallInfo | null, version: string): Step[] {
  switch (install?.kind) {
    case "windows-installer":
      return windowsSteps(version);
    case "appimage":
      return appImageSteps(install, version);
    case "macos-app":
      return macSteps(install, version);
    case "deb":
      return debSteps(install, version);
    case "source":
      return [
        { text: t("help.update.source.pull"), command: "git pull" },
        { text: t("help.update.source.sync"), command: "uv sync" },
        restart(install.service, "systemctl --user restart neoaprs"),
      ];
    default:
      // Install kind unknown, or a wheel install: the release page lists the supported installs.
      return [
        { text: t("help.update.release_page"), link: { href: releaseNotes(version), label: `NeoAPRS ${version}` } },
      ];
  }
}

/**
 * What Update now is doing, in words: null while nothing runs (the button shows) or it has failed.
 */
export function progressText(
  state: UpdateState,
  kind: InstallInfo["kind"] | undefined,
  connected: boolean,
): string | null {
  switch (state.state) {
    case "downloading":
      return state.percent === null
        ? t("help.update.downloading_size", { mb: Math.round(state.downloaded / 1e6) })
        : t("help.update.downloading", { percent: state.percent });
    case "verifying":
      return t("help.update.verifying");
    case "installing":
      return t("help.update.installing");
    case "restarting":
      if (!connected) return t("help.update.reconnecting");
      return t(kind === "windows-installer" ? "help.update.restarting_installer" : "help.update.restarting");
    default:
      return null;
  }
}

const PROBLEMS = {
  download: "help.update.problem.download",
  unverified: "help.update.problem.unverified",
  checksum: "help.update.problem.checksum",
  install: "help.update.problem.install",
  no_restart: "help.update.problem.no_restart",
} as const satisfies Record<Exclude<UpdateState["problem"], "">, MessageId>;

/** Why Update now failed, in words; empty if it did not. */
export function problemText(problem: UpdateState["problem"]): string {
  return problem === "" ? "" : t(PROBLEMS[problem]);
}

/** Whether Update now is in progress (the button gives way to the progress). */
export const updateRunning = (state: UpdateState | null): boolean =>
  state !== null && ["downloading", "verifying", "installing", "restarting"].includes(state.state);
