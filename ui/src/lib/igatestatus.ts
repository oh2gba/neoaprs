// What the Internet group of the Settings tab says in plain words (components/IgateStatus.vue): one line ("Connected, receiving"); the state as a mark is the top bar's (lib/pills.ts).
// The group has one switch, Receive only: the stations of APRS-IS round the map's radius on the map, nothing sent. A connection that is up is receiving, whatever the daemon says of its login.
import { t } from "@/i18n";
import type { IgateState } from "@/protocol/protocol";

/** Off, connecting, or receiving (a login that is up, verified or not). */
type IgateLook = "off" | "connecting" | "receiving";

const igateLook = (state: IgateState["state"]): IgateLook => (state === "off" || state === "connecting" ? state : "receiving");

/**
 * The one line: "Off", "Connecting to rotate.aprs2.net:14580…", "Not connected: Connection refused", "Connected, receiving". `values` are the settings in force, key to text: the server is the one the daemon says, else the setting.
 */
export function igateStatus(igate: IgateState, values: Readonly<Record<string, string>>): string {
  switch (igateLook(igate.state)) {
    case "off":
      return t("settings.igate.line.off");
    case "receiving":
      return t("settings.igate.line.receiving");
    default:
      return igate.problem === ""
        ? t("settings.igate.line.connecting", { server: igate.server || (values["igate/server"] ?? "") })
        : t("settings.igate.line.not_connected_why", { why: igate.problem });
  }
}
