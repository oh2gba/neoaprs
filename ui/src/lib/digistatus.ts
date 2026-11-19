// What the Digipeater group of the Settings tab says in plain words, for a radio's own digipeater (the fill-in, `digiLook`) and for a pair of radios (`pairLook`) (components/DigipeaterStatus.vue), in the words and colours of the radio's status row (components/StatusFold.vue): "on" with how many packets it repeated and when the last went ("12 packets repeated · last 3 min ago",
// "None repeated yet"), or "off" in the warn colour while RX only is ticked, and behind the arrow since when it counts and, if the burst limit held frames back, how many. The count is the daemon's, since it started (the radio's row).
import { t } from "@/i18n";
import { ageText, dateTimeText } from "@/lib/format";
import type { PassStats, RadioRow, TncStats } from "@/protocol/protocol";

export interface DigiLook {
  state: string;
  /** the class that colours the state (the radio's `tnc-*`) */
  tone: string;
  line: string;
  /** behind the arrow: since when it counts, and the frames the burst limit held back (empty when none) */
  since: string;
  held: string;
}

/** The look for the counters of the TNC, when the daemon started (`startedAt`, ISO), the time now and whether RX only is ticked (nothing is repeated). */
export function digiLook(tnc: Pick<RadioRow, "stats">, startedAt: string | null, nowMs: number, rxOnly: boolean): DigiLook {
  const { digipeated, digipeated_at, digipeat_held } = tnc.stats;
  const behind = {
    since: startedAt === null ? "" : t("settings.digi.fold.since", { when: dateTimeText(startedAt) }),
    held: digipeat_held > 0 ? t("settings.digi.fold.held", { n: digipeat_held }) : "",
  };
  if (rxOnly) return { state: t("settings.digi.off"), tone: "tnc-waiting", line: t("settings.digi.line.rx_only"), ...behind };
  const line =
    digipeated === 0 || digipeated_at === null
      ? t("settings.digi.line.none")
      : t("settings.digi.line.count", { n: digipeated, span: ageText(digipeated_at, nowMs) });
  return { state: t("settings.digi.on"), tone: "tnc-connected", line, ...behind };
}

/** One radio of a pair: its id, what the page calls it (its box's legend) and its counts (`stats.passed`: what the pair passed onto it, by the radio heard on). */
interface PairEnd {
  id: number;
  name: string;
  readonly stats: TncStats;
}

/** A pair of radios, in the order of their boxes. */
export interface PairLink {
  first: PairEnd;
  second: PairEnd;
}

/** The look of a pair's status row: the fill-in row's state, line and since, and behind the arrow what went each way and, by the radio it was for, what was held back and what was too long (empty when none). */
export interface PairLook {
  state: string;
  tone: string;
  line: string;
  since: string;
  ways: string;
  held: readonly string[];
  tooLong: readonly string[];
}

/** What the pair passed onto `to` from `from`: its entry of `to`'s counts, or nothing yet. */
const passedOnto = (to: PairEnd, from: PairEnd): Pick<PassStats, "sent" | "sent_at" | "held" | "too_long"> =>
  to.stats.passed.find((entry) => entry.heard_on === from.id) ?? { sent: 0, sent_at: null, held: 0, too_long: 0 };

/** The look for a pair's counts, both ways together, when the daemon started (`startedAt`, ISO), the time now and whether RX only is ticked (nothing is passed). */
export function pairLook(pair: PairLink, startedAt: string | null, nowMs: number, rxOnly: boolean): PairLook {
  const ends = [pair.first, pair.second] as const;
  const onto = [passedOnto(pair.first, pair.second), passedOnto(pair.second, pair.first)] as const;
  const sent = onto[0].sent + onto[1].sent;
  const ats = onto.map((way) => way.sent_at).filter((at): at is string => at !== null);
  const latest = ats.sort((a, b) => Date.parse(b) - Date.parse(a))[0] ?? null;
  const behind = {
    since: startedAt === null ? "" : t("settings.digi.fold.since", { when: dateTimeText(startedAt) }),
    ways: sent > 0 ? t("settings.pair.fold.each_way", { n: onto[0].sent, first: pair.first.name, m: onto[1].sent, second: pair.second.name }) : "",
    held: onto.flatMap((way, i) => (way.held > 0 ? [t("settings.pair.fold.held", { n: way.held, radio: ends[i].name })] : [])),
    tooLong: onto.flatMap((way, i) => (way.too_long > 0 ? [t("settings.pair.fold.too_long", { n: way.too_long, radio: ends[i].name })] : [])),
  };
  if (rxOnly) return { state: t("settings.digi.off"), tone: "tnc-waiting", line: t("settings.digi.line.rx_only"), ...behind };
  const line = sent === 0 || latest === null ? t("settings.digi.line.none") : t("settings.digi.line.count", { n: sent, span: ageText(latest, nowMs) });
  return { state: t("settings.digi.on"), tone: "tnc-connected", line, ...behind };
}
