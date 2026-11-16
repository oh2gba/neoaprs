// What the Internet stations group of the Settings tab says in plain words (components/IgateStatus.vue), in the words and colours of the radio's status row (components/StatusFold.vue): the state as a word (connected, connecting, waiting), one quiet line ("Connected: rotate.aprs2.net · 42 stations within 50 km",
// "Connecting to rotate.aprs2.net:14580…", "Not connected: the server cannot be reached") and the two lines behind the arrow (the server, the filter). The state as a mark is the top bar's (lib/pills.ts).
// The group has one tickbox, Enable: the stations of APRS-IS round the map's radius on the map, nothing sent. A connection that is up is connected, whatever the daemon says of its login.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { channelsOf } from "@/lib/channels";
import type { IgateState, StationRow } from "@/protocol/protocol";

export interface IgateLook {
  /** the word of the state, as the radio's: connected, connecting, waiting (not connected, and why) */
  state: string;
  /** the class that colours it (the radio's `tnc-*`) */
  tone: string;
  /** the one line */
  line: string;
  /** behind the arrow: the server, and the filter that the map's radius is */
  server: string;
  filter: string;
}

/** How many stations are known from the internet (heard over it, whatever else they were heard by). */
export function internetStations(rows: Iterable<StationRow>): number {
  let n = 0;
  for (const row of rows) if (channelsOf(row).includes("is")) n++;
  return n;
}

const hostOf = (server: string): string => server.split(":")[0] ?? server;

/** Why the iGate is not connected, as the line says it: the words of each reason the daemon gives; "Not connected" for one the page has no words for. */
const REASON_LINES: Partial<Record<IgateState["reason"], MessageId>> = {
  no_server: "settings.igate.line.no_server",
  no_call: "settings.igate.line.no_call",
  unreachable: "settings.igate.line.unreachable",
  offline: "settings.igate.line.offline",
  not_server: "settings.igate.line.not_server",
  lost: "settings.igate.line.lost",
};
const reasonLine = (reason: IgateState["reason"]): string => t(REASON_LINES[reason] ?? "settings.tnc.not_connected");

/** The look for the state the daemon told, the settings in force (`values`, key to text) and the number of stations known from the internet. */
export function igateLook(igate: IgateState, values: Readonly<Record<string, string>>, stations: number): IgateLook {
  const setting = (values["igate/server"] ?? "").trim();
  const km = values["map/radius_km"] ?? "";
  const server =
    igate.server && igate.server !== hostOf(setting) ? t("settings.igate.fold.named", { name: igate.server, server: setting }) : setting || igate.server;
  const behind = { server: t("settings.igate.fold.server", { server }), filter: t("settings.igate.fold.filter", { km }) };
  if (igate.state === "off") return { state: t("settings.tnc.state.stopped"), tone: "tnc-stopped", line: t("settings.igate.line.off"), ...behind };
  if (igate.state === "connecting") {
    const waiting = igate.reason !== "";
    const line = waiting ? reasonLine(igate.reason) : t("settings.igate.line.connecting", { server: igate.server || setting });
    return waiting
      ? { state: t("settings.tnc.state.waiting"), tone: "tnc-waiting", line, ...behind }
      : { state: t("settings.tnc.state.connecting"), tone: "tnc-connecting", line, ...behind };
  }
  const line = t("settings.igate.line.receiving", { server: hostOf(setting) || igate.server, n: stations, km });
  return { state: t("settings.tnc.state.connected"), tone: "tnc-connected", line, ...behind };
}
