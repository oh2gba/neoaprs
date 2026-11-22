// What an own receiver's state says in plain words (Settings, Map: components/SettingsLayer.vue),
// like lib/gpsstatus.ts for a GPS: a pill word and one line. The state is the daemon's
// (`MapLayer.receiver`).
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { ageText } from "@/lib/format";
import type { LayerName } from "@/lib/layers/sources";
import type { LayerReceiver } from "@/protocol/protocol";

/** The pill's word and colour (the radio's connection colours: found is green, others warn). */
const PILLS: Record<LayerReceiver["state"], { text: MessageId; tone: string }> = {
  looking: { text: "layers.receiver.state.looking", tone: "tnc-connecting" },
  receiving: { text: "layers.receiver.state.receiving", tone: "tnc-connected" },
  no_answer: { text: "layers.receiver.state.no_answer", tone: "tnc-waiting" },
};

/** What a receiver that has not reported yet is: looking. */
const LOOKING: LayerReceiver = { state: "looking", things: 0, heard_at: null };

export interface ReceiverLook {
  state: string;
  tone: string;
  line: string;
}

/**
 * The line: "Looking for the receiver", "Receiving: 42 aircraft, 3 s ago", "No answer from the
 * receiver", etc.
 */
function lineOf(layer: LayerName, receiver: LayerReceiver, nowMs: number): string {
  if (receiver.state === "looking") return t("layers.receiver.line.looking");
  if (receiver.state === "no_answer") return t("layers.receiver.line.no_answer");
  if (receiver.heard_at === null) return t(layer === "ships" ? "layers.receiver.line.ships_none" : "layers.receiver.line.aircraft_none");
  const values = { n: receiver.things, span: ageText(receiver.heard_at, nowMs) };
  return layer === "ships" ? t("layers.receiver.line.ships", values) : t("layers.receiver.line.aircraft", values);
}

/** The pill and line of a layer's own receiver (`receiver` null: not reported, so looking). */
export function receiverLook(layer: LayerName, receiver: LayerReceiver | null, nowMs: number): ReceiverLook {
  const state = receiver ?? LOOKING;
  const pill = PILLS[state.state];
  return { state: t(pill.text), tone: pill.tone, line: lineOf(layer, state, nowMs) };
}
