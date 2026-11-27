// What the Internet (APRS-IS) group of the Settings tab says in plain words
// (components/IgateStatus.vue), in the words and colours of the radio's status row
// (components/StatusFold.vue): the state as a word (connected, connecting, waiting), one quiet line
// ("rotate.aprs2.net · 42 stations within 50 km", "rotate.aprs2.net · 812 packets sent",
// "Connecting to rotate.aprs2.net:14580…") and the lines behind the arrow (the server, the filter
// while the stations are shown, what was sent while what the radios hear is sent). The state as a
// mark is the top bar's (lib/pills.ts). Show Internet stations alone never speaks of sending.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { channelsOf } from "@/lib/channels";
import type { IgateState, StationRow } from "@/protocol/protocol";

export interface IgateLook {
  /** The word of the state, as the radio's: connected, connecting, waiting (not connected, and
   * why). */
  state: string;
  /** The class that colours it (the radio's `tnc-*`). */
  tone: string;
  /** The one line. */
  line: string;
  /** Behind the arrow: the server, the filter that the map's radius is (empty while the stations
   * are not shown), and what was sent (empty while nothing is sent). */
  server: string;
  filter: string;
  sent: string;
}

/** How many stations are known from the internet (heard over it, whatever else heard them). */
export function internetStations(rows: Iterable<StationRow>): number {
  let n = 0;
  for (const row of rows) if (channelsOf(row).includes("is")) n++;
  return n;
}

const hostOf = (server: string): string => server.split(":")[0] ?? server;

/** Why the login is not up, as the line says it: the words for each reason the daemon gives;
 * "Not connected" for one the page has no words for. */
const REASON_LINES: Partial<Record<IgateState["reason"], MessageId>> = {
  no_server: "settings.igate.line.no_server",
  no_call: "settings.igate.line.no_call",
  unreachable: "settings.igate.line.unreachable",
  offline: "settings.igate.line.offline",
  not_server: "settings.igate.line.not_server",
  lost: "settings.igate.line.lost",
};
const reasonLine = (reason: IgateState["reason"]): string => t(REASON_LINES[reason] ?? "settings.tnc.not_connected");

/** Behind the arrow: the server (by the name it gave, with the setting), the filter while the
 * stations are shown, and what was sent while what the radios hear is sent. */
function behindOf(igate: IgateState, setting: string, km: string): Pick<IgateLook, "server" | "filter" | "sent"> {
  const server =
    igate.server && igate.server !== hostOf(setting)
      ? t("settings.igate.fold.named", { name: igate.server, server: setting })
      : setting || igate.server;
  return {
    server: t("settings.igate.fold.server", { server }),
    filter: igate.enabled ? t("settings.igate.fold.filter", { km }) : "",
    sent: igate.gate ? t("settings.igate.fold.sent", { n: igate.gated }) : "",
  };
}

/** The state word, its colour and the line while it is not logged in: off, connecting, waiting. */
function notUp(igate: IgateState, setting: string): Pick<IgateLook, "state" | "tone" | "line"> {
  if (igate.state === "off")
    return { state: t("settings.tnc.state.stopped"), tone: "tnc-stopped", line: t("settings.igate.line.off") };
  if (igate.reason !== "")
    return { state: t("settings.tnc.state.waiting"), tone: "tnc-waiting", line: reasonLine(igate.reason) };
  return {
    state: t("settings.tnc.state.connecting"),
    tone: "tnc-connecting",
    line: t("settings.igate.line.connecting", { server: igate.server || setting }),
  };
}

/** The look for the state the daemon reported, the settings in force (`values`, key to text) and
 * the number of stations known from the internet. */
export function igateLook(igate: IgateState, values: Readonly<Record<string, string>>, stations: number): IgateLook {
  const setting = (values["igate/server"] ?? "").trim();
  const km = values["map/radius_km"] ?? "";
  const behind = behindOf(igate, setting, km);
  if (igate.state === "off" || igate.state === "connecting") return { ...notUp(igate, setting), ...behind };
  if (igate.gate && igate.state === "unverified")
    return {
      state: t("settings.tnc.state.waiting"),
      tone: "tnc-waiting",
      line: t("settings.igate.line.refused"),
      ...behind,
    };
  const host = hostOf(setting) || igate.server;
  const line = igate.enabled
    ? t("settings.igate.line.receiving", { server: host, n: stations, km })
    : t("settings.igate.line.sending", { server: host, n: igate.gated });
  return { state: t("settings.tnc.state.connected"), tone: "tnc-connected", line, ...behind };
}
