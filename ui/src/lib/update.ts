// What to do to update, for the way this copy was installed (the daemon says: `install` of its hello). The steps are data, so that the panel (components/UpdatePanel.vue) only draws them: a line of words, a command to copy, a file to download.
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
  return service ? { text: "Restart the service", command } : { text: "Quit NeoAPRS and start it again" };
}

/** The steps to the version `version` for a copy installed as `install`; null while the daemon has not said how (then the release page is all there is). */
export function updateHelp(install: InstallInfo | null, version: string): UpdateHelp {
  switch (install?.kind) {
    case "windows-installer":
      return {
        steps: [
          { text: "Download the installer", link: { href: installerUrl(version), label: `NeoAPRS-Setup-${version}.exe` } },
          { text: "Run it: it replaces the running NeoAPRS and starts it again" },
        ],
      };
    case "appimage": {
      const file = `./${appImageName(version)}`;
      const steps: Step[] = [
        { text: "Download the new file", link: { href: appImageUrl(version), label: appImageName(version) } },
        { text: "Make it executable", command: `chmod +x ${appImageName(version)}` },
        { text: "Quit NeoAPRS and start the new file", command: file },
      ];
      if (install.service)
        steps.push({ text: "A service runs the old file: from where you keep the new one, run this once", command: `${file} service install` });
      if (install.appimage) steps.push({ text: `Delete the old file, ${fileName(install.appimage)}` });
      return { steps };
    }
    case "deb": {
      // the machine's architecture is known for amd64 and arm64; for any other the release page lists the files, and the command takes whichever one was downloaded
      const file = install.arch ? debName(version, install.arch) : `neoaprs_${version}_*.deb`;
      return {
        steps: [
          install.arch
            ? { text: "Download the new package", link: { href: debUrl(version, install.arch), label: file } }
            : { text: "Download the package for your machine from the release page", link: { href: releaseNotes(version), label: `NeoAPRS ${version}` } },
          { text: "Install it over the old one", command: `sudo apt install ./${file}` },
          restart(install.service, "systemctl --user restart neoaprs"),
        ],
      };
    }
    case "uv-tool":
      return { steps: [{ text: "Run the install line again: it updates NeoAPRS and restarts its service", command: INSTALL_LINE }] };
    case "pip":
      return {
        steps: [
          { text: "In its environment", command: "pip install -U neoaprs" },
          { text: "or, with uv", command: "uv pip install -U neoaprs" },
          restart(install.service, "neoaprs service install"),
        ],
      };
    case "source":
      return {
        steps: [
          { text: "In the folder of the clone", command: "git pull" },
          { text: "Bring the environment up to date", command: "uv sync" },
          restart(install.service, "systemctl --user restart neoaprs"),
        ],
      };
    default:
      return { steps: [{ text: "Get the new version from the release page", link: { href: releaseNotes(version), label: `NeoAPRS ${version}` } }] };
  }
}
