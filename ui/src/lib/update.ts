// What to do to update, for the way this copy was installed (the daemon says: `install` of its hello). The steps are data, so that the panel (components/UpdatePanel.vue) only draws them: a line of words (made in the language of the page when they are asked for), a command to copy, a file to download.
import { t } from "@/i18n";
import type { InstallInfo } from "@/protocol/protocol";

const RELEASES = "https://github.com/oh2gba/neoaprs/releases";
export const INSTALL_LINE = "curl -LsSf https://github.com/oh2gba/neoaprs/releases/latest/download/install.sh | sh";

interface Step {
  text: string;
  /** a command to run, with a button that copies it */
  command?: string;
  /** a file to download */
  link?: { href: string; label: string };
}

export interface UpdateHelp {
  steps: Step[];
}

export const releaseNotes = (version: string): string => `${RELEASES}/tag/v${version}`;
export const installerUrl = (version: string): string => `${RELEASES}/download/v${version}/NeoAPRS-Setup-${version}.exe`;
const appImageName = (version: string): string => `NeoAPRS-${version}-x86_64.AppImage`;
export const appImageUrl = (version: string): string => `${RELEASES}/download/v${version}/${appImageName(version)}`;
export const debName = (version: string, arch: string): string => `neoaprs_${version}_${arch}.deb`;
export const debUrl = (version: string, arch: string): string => `${RELEASES}/download/v${version}/${debName(version, arch)}`;

/** The last part of a path of either kind. */
function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

/** Quits and starts again: a service is restarted with `command`, a program started by hand is quit and started. */
function restart(service: boolean, command: string): Step {
  return service ? { text: t("help.update.restart_service"), command } : { text: t("help.update.restart") };
}

/** The steps to the version `version` for a copy installed as `install`; null while the daemon has not said how (then the release page is all there is). */
export function updateHelp(install: InstallInfo | null, version: string): UpdateHelp {
  switch (install?.kind) {
    case "windows-installer":
      return {
        steps: [
          { text: t("help.update.download_installer"), link: { href: installerUrl(version), label: `NeoAPRS-Setup-${version}.exe` } },
          { text: t("help.update.run_installer") },
        ],
      };
    case "appimage": {
      const file = `./${appImageName(version)}`;
      const steps: Step[] = [
        { text: t("help.update.download_file"), link: { href: appImageUrl(version), label: appImageName(version) } },
        { text: t("help.update.make_executable"), command: `chmod +x ${appImageName(version)}` },
        { text: t("help.update.start_file"), command: file },
      ];
      if (install.service) steps.push({ text: t("help.update.service_file"), command: `${file} service install` });
      if (install.appimage) steps.push({ text: t("help.update.delete_old", { name: fileName(install.appimage) }) });
      return { steps };
    }
    case "deb": {
      // the machine's architecture is known for amd64 and arm64; for any other the release page lists the files, and the command takes whichever one was downloaded
      const file = install.arch ? debName(version, install.arch) : `neoaprs_${version}_*.deb`;
      return {
        steps: [
          install.arch
            ? { text: t("help.update.download_package"), link: { href: debUrl(version, install.arch), label: file } }
            : { text: t("help.update.download_package_here"), link: { href: releaseNotes(version), label: `NeoAPRS ${version}` } },
          { text: t("help.update.install_package"), command: `sudo apt install ./${file}` },
          restart(install.service, "systemctl --user restart neoaprs"),
        ],
      };
    }
    case "uv-tool":
      return { steps: [{ text: t("help.update.install_line"), command: INSTALL_LINE }] };
    case "pip":
      return {
        steps: [
          { text: t("help.update.in_environment"), command: "pip install -U neoaprs" },
          { text: t("help.update.or_uv"), command: "uv pip install -U neoaprs" },
          restart(install.service, "neoaprs service install"),
        ],
      };
    case "source":
      return {
        steps: [
          { text: t("help.update.in_clone"), command: "git pull" },
          { text: t("help.update.sync"), command: "uv sync" },
          restart(install.service, "systemctl --user restart neoaprs"),
        ],
      };
    default:
      return { steps: [{ text: t("help.update.release_page"), link: { href: releaseNotes(version), label: `NeoAPRS ${version}` } }] };
  }
}
