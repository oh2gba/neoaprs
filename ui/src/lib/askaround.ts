// Asking around (the first box of the Nearby tab, NearbyAsk.vue): the kinds of general query the page offers, the query each sends, how long Ask waits after a query of a kind, and the two quiet lines under it. The daemon sends the
// query (services/generalask.py) and holds a kind to one a minute; the answers are ordinary packets, so the lines say where they arrive, and the second counts the stations that were quiet before the query and spoke after it
// (the topic `general`: most are answers, but nothing tells an answer from a beacon that fell then, and the line says no more than it knows).
import { t } from "@/i18n";
import { hourMinuteText } from "@/lib/format";
import { LIMITS } from "@/protocol/lists";
import type { GeneralAsked, GeneralState } from "@/protocol/protocol";

export type GeneralKind = GeneralAsked["kind"];

/** The kinds, in the order the choice offers them: who is around (?APRS?), the iGates (?IGATE?), the weather stations (?WX?). */
export const GENERAL_KINDS: readonly GeneralKind[] = ["aprs", "igate", "wx"];

/** The query a kind sends, as the daemon writes it (`?APRS?`). */
export const queryOf = (kind: GeneralKind): string => LIMITS.general.queries[kind];

/** The seconds before a query of the kind may go again, 0 when it may: one a minute of each kind, the daemon's rule. */
export function generalWait(state: GeneralState | null, kind: GeneralKind, nowMs: number): number {
  const asked = state?.asked.find((a) => a.kind === kind);
  if (asked === undefined) return 0;
  return Math.max(0, Math.ceil((Date.parse(asked.at) + LIMITS.general.askEverySec * 1000 - nowMs) / 1000));
}

export interface AskLines {
  /** what was asked, when and by what path, and where the answers arrive; before a query what Ask does; a refusal with its reason */
  line: string;
  /** the hover of the first line: the query and the whole path, RFONLY included */
  title: string;
  /** the first line is a refusal */
  refused: boolean;
  /** how many stations that were quiet before the query spoke after it; "" before a query */
  count: string;
  /** the hover of the count: their calls, and what the count can and cannot tell */
  countTitle: string;
}

const RF_ONLY = LIMITS.path.rfOnly;

/** The two lines under Ask: the latest query of any kind (the topic lists the last of each, the oldest first), or the refusal of the last Ask while there is one. */
export function askLines(state: GeneralState | null, refusal: string, nowMs: number): AskLines {
  const latest = state?.asked.at(-1);
  if (refusal !== "") return { line: t("nearby.ask_refused", { reason: refusal }), title: refusal, refused: true, count: "", countTitle: "" };
  if (latest === undefined) return { line: t("nearby.ask_help"), title: "", refused: false, count: "", countTitle: "" };
  const hops = latest.path.filter((hop) => hop !== RF_ONLY);
  const path = hops.length > 0 ? hops.join(",") : t("route.direct");
  const time = hourMinuteText(latest.at);
  const n = latest.new.length;
  const quiet = { n, min: LIMITS.general.quietMin, after: Math.round(LIMITS.general.countSec / 60) };
  const counting = Date.parse(latest.until) > nowMs;
  return {
    line: t(`nearby.ask_sent.${latest.kind}`, { time, path }),
    title: `${latest.query} ${latest.path.join(",") || t("route.direct")}`,
    refused: false,
    count: t(counting ? "nearby.ask_new_counting" : "nearby.ask_new", quiet),
    countTitle: n > 0 ? t("nearby.ask_new_title", { calls: latest.new.join(", ") }) : t("nearby.ask_new_note", { min: LIMITS.general.quietMin }),
  };
}
