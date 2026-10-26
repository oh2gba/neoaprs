// What the Digipeater group of the Settings tab says in plain words (components/DigipeaterStatus.vue), in the words and colours of the radio's status row (components/StatusFold.vue): "on" with how many packets it repeated and when the last went ("12 packets repeated · last 3 min ago",
// "None repeated yet"), or "off" in the warn colour while RX only is ticked, and behind the arrow since when it counts and, if the burst limit held frames back, how many. The count is the daemon's, since it started (the topic `tnc`).
import { t } from "@/i18n";
import { ageText, dateTimeText } from "@/lib/format";
import type { TncState } from "@/protocol/protocol";

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
export function digiLook(tnc: TncState, startedAt: string | null, nowMs: number, rxOnly: boolean): DigiLook {
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
