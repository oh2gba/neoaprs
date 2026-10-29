// The alert of the page itself for a message to us (the daemon's alert command runs on the server, which is not where the person is when the page is open from a laptop or a phone): which messages are
// new, the words of the notification and of the browser tab, and what a page opened from this address does by default. The sound is lib/chime.ts, the switches and the notification
// composables/useBrowserAlerts.ts, the browser tab composables/useTabAlert.ts.
import { t } from "@/i18n";
import type { MessageRow } from "@/protocol/protocol";

/** Whether the page is open on the machine it is served from (localhost, 127.x.x.x, ::1): there the daemon's own alert and the desktop app already notify. */
export function isLoopbackHost(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  return host === "localhost" || host.endsWith(".localhost") || host === "::1" || /^127(\.\d{1,3}){3}$/.test(host);
}

/** A message that came in, addressed to us, as opposed to one of ours or one we only overheard. */
function isForUs(row: MessageRow): boolean {
  return row.direction === "in" && row.state === "received";
}

/** What the page has already told the person: ids up to `mark`. `null` before the first state of the topic, which is only the baseline. */
export interface Scan {
  mark: number | null;
  /** the messages to us that arrived after the mark, the oldest first */
  fresh: MessageRow[];
}

/** The messages to us that were not there before (ids above the mark), and the new mark: the highest id of any row, whoever it is for. The first scan alerts nothing: what the page loaded with is not new. Rows whose highest id is below the mark are a database that was restored or reset: they are the new baseline, so that the messages after them are not taken for seen. */
export function scan(rows: Iterable<MessageRow>, mark: number | null): Scan {
  const all = [...rows];
  const top = all.reduce((most, row) => Math.max(most, row.id), 0);
  if (mark === null || (all.length > 0 && top < mark)) return { mark: top, fresh: [] };
  return { mark: Math.max(top, mark), fresh: all.filter((row) => row.id > mark && isForUs(row)).sort((a, b) => a.id - b.id) };
}

/** The title of the notification. */
export function notificationTitle(from: string): string {
  return t("settings.alert.notification_title", { call: from });
}

/** The text the browser tab shows while it is alerting: "✉ OH2DPN" for a message, "🔔 OH2XYZ" for an alert set on a station (which is no message). */
export function flashTitle(from: string, bell = false): string {
  return `${bell ? "🔔" : "✉"} ${from}`;
}

/** The icon of the browser tab with a red dot at its corner. */
export const DOT_ICON =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ccircle cx='8' cy='8' r='7' fill='%231565c0'/%3E%3Ccircle cx='8' cy='8' r='2.5' fill='white'/%3E%3Ccircle cx='12' cy='4' r='3.5' fill='%23d32f2f' stroke='white' stroke-width='1'/%3E%3C/svg%3E";
