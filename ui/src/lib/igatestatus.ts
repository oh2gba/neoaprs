// What the iGate group of the Settings tab says in plain words (components/IgateStatus.vue), as the radio status does for the TNC (lib/tncstatus.ts): a word for the state on a pill, one line ("Connected to T2FINLAND, 1234 packets
// gated, last 12 s ago"), the hover title with what was heard and not gated, and the address of the page where a passcode is requested.
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { ageText } from "@/lib/format";
import type { IgateState } from "@/protocol/protocol";

/**
 * The NeoAPRS author's page where an APRS-IS passcode is requested for a call. APRS-IS policy (https://www.aprs-is.net/Connecting.aspx) says "It is the responsibility of each software author to provide the proper passcode to their
 * individual users on a request basis", and the passcode is never worked out by NeoAPRS: the person asks, and the answer comes by e-mail.
 */
export const PASSCODE_URL = "https://oh2gba.eu/neoaprs/passcode";

/** The request page, with the base call of `station/call` (the passcode does not depend on the SSID) as `?call=` when there is one. */
export function passcodeLink(call: string): string {
  const base = call.trim().split("-")[0] ?? "";
  return base === "" ? PASSCODE_URL : `${PASSCODE_URL}?call=${encodeURIComponent(base)}`;
}

const STATES: Record<IgateState["state"], MessageId> = {
  off: "settings.igate.state.off",
  connecting: "settings.igate.state.connecting",
  connected: "settings.igate.state.connected",
  unverified: "settings.igate.state.unverified",
};

/** The word on the pill for the state of the iGate. */
export const igateStateText = (state: IgateState["state"]): string => t(STATES[state]);

/**
 * The one line: "Off", "Waiting: the passcode is not set", "Connecting to rotate.aprs2.net:14580…", "Not connected: Connection refused", "The server did not accept the passcode…", "Connected to T2FINLAND, no packet gated yet",
 * "Connected to T2FINLAND, 1234 packets gated, last 12 s ago". `values` are the settings in force, key to text: what is missing is told from them, and the daemon's own reason (English) only when it is a connection's.
 */
export function igateStatus(igate: IgateState, values: Readonly<Record<string, string>>, nowMs: number): string {
  const server = igate.server || (values["igate/server"] ?? "");
  switch (igate.state) {
    case "off":
      return t("settings.igate.line.off");
    case "unverified":
      return t("settings.igate.line.unverified", { call: values["station/call"] ?? "" });
    case "connected":
      return igate.last_gated_at === null
        ? t("settings.igate.line.connected_none", { server })
        : t("settings.igate.line.connected", { server, n: igate.gated, span: ageText(igate.last_gated_at, nowMs) });
    default:
      if ((values["igate/password"] ?? "") === "") return t("settings.igate.line.need_password");
      return igate.problem === "" ? t("settings.igate.line.connecting", { server }) : t("settings.igate.line.not_connected_why", { why: igate.problem });
  }
}

/** The hover title of the line: what was heard and not put on APRS-IS, by reason ("Not gated: already via the internet: 31, duplicate: 6"); empty when nothing was left out. */
export function igateCounts(igate: IgateState): string {
  const parts = Object.entries(igate.dropped)
    .sort((a, b) => b[1] - a[1])
    .map(([reason, n]) => t("settings.igate.count", { reason: reasonText(reason), n }));
  return parts.length === 0 ? "" : t("settings.igate.counts", { list: parts.join(", ") });
}

const REASONS: Record<string, MessageId> = {
  tcpip: "settings.igate.reason.tcpip",
  nogate: "settings.igate.reason.nogate",
  query: "settings.igate.reason.query",
  source: "settings.igate.reason.source",
  own: "settings.igate.reason.own",
  newline: "settings.igate.reason.newline",
  long: "settings.igate.reason.long",
  frame: "settings.igate.reason.frame",
  duplicate: "settings.igate.reason.duplicate",
  offline: "settings.igate.reason.offline",
};

const reasonText = (reason: string): string => {
  const id = REASONS[reason];
  return id === undefined ? reason : t(id);
};
