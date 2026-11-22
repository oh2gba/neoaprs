// Asking around (NearbyAsk.vue): the kinds of general query, the query each sends, how long Ask
// waits after one, and the two quiet lines under it. The daemon sends the query
// (services/generalask.py) and limits a kind to one a minute. Answers are ordinary packets; the
// second line counts stations that were quiet before the query and spoke after it (topic
// `general`), without claiming they are answers.
import { t } from "@/i18n";
import { hourMinuteText } from "@/lib/format";
import { LIMITS } from "@/protocol/lists";
import type { GeneralAsked, GeneralState } from "@/protocol/protocol";

export type GeneralKind = GeneralAsked["kind"];

/**
 * The kinds in the order offered: who is around (?APRS?), iGates (?IGATE?), weather stations
 * (?WX?).
 */
export const GENERAL_KINDS: readonly GeneralKind[] = ["aprs", "igate", "wx"];

/** The query a kind sends, as the daemon writes it (`?APRS?`). */
export const queryOf = (kind: GeneralKind): string => LIMITS.general.queries[kind];

/**
 * The seconds before a query of this kind may go out on these radios, 0 if it may now. The daemon
 * allows one a minute per kind per radio and waits for every radio (no radios given: any).
 */
export function generalWait(state: GeneralState | null, kind: GeneralKind, radios: readonly number[], nowMs: number): number {
  const sent = (state?.by_radio ?? []).filter((one) => one.kind === kind && (radios.length === 0 || radios.includes(one.radio)));
  const latest = Math.max(0, ...sent.map((one) => Date.parse(one.at)));
  return sent.length === 0 ? 0 : Math.max(0, Math.ceil((latest + LIMITS.general.askEverySec * 1000 - nowMs) / 1000));
}

export interface AskLines {
  /**
   * what was asked, when, by what path and where answers arrive; before a query, what Ask
   * does; or a refusal
   */
  line: string;
  /** the first line's hover: the query and the whole path, RFONLY included */
  title: string;
  /** the first line is a refusal */
  refused: boolean;
  /** how many quiet stations spoke after the query; "" before a query */
  count: string;
  /** the count's hover: their calls, and what the count can and cannot tell */
  countTitle: string;
}

const RF_ONLY = LIMITS.path.rfOnly;

/** The two lines under Ask: the latest query of any kind, or the refusal of the last Ask. */
export function askLines(state: GeneralState | null, refusal: string, nowMs: number): AskLines {
  const latest = state?.asked.at(-1);
  if (refusal !== "") return { line: t("nearby.ask_refused", { reason: refusal }), title: refusal, refused: true, count: "", countTitle: "" };
  if (latest === undefined) return { line: t("nearby.ask_help"), title: "", refused: false, count: "", countTitle: "" };
  const hops = (latest.path ?? []).filter((hop) => hop !== RF_ONLY);
  const time = hourMinuteText(latest.at);
  const n = latest.new.length;
  const quiet = { n, min: LIMITS.general.quietMin, after: Math.round(LIMITS.general.countSec / 60) };
  const counting = Date.parse(latest.until) > nowMs;
  // path null: each radio used its own path and they differ, so the line names none.
  const line =
    latest.path === null
      ? t(`nearby.ask_sent_own.${latest.kind}`, { time })
      : t(`nearby.ask_sent.${latest.kind}`, { time, path: hops.length > 0 ? hops.join(",") : t("route.direct") });
  return {
    line,
    title: latest.path === null ? latest.query : `${latest.query} ${latest.path.join(",") || t("route.direct")}`,
    refused: false,
    count: t(counting ? "nearby.ask_new_counting" : "nearby.ask_new", quiet),
    countTitle: n > 0 ? t("nearby.ask_new_title", { calls: latest.new.join(", ") }) : t("nearby.ask_new_note", { min: LIMITS.general.quietMin }),
  };
}
