// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { beacon as source } from "@/i18n/en/beacon";
import type { Message } from "@/i18n/message";

export const beacon: Record<keyof typeof source, Message> = {
  "beacon.last_beacon": "最後のビーコン",
  "beacon.not_yet": "まだ",
  "beacon.beacon_now": "今すぐビーコン",
  "beacon.status": "ステータス",
  "beacon.send_status_now": "今すぐステータスを送信",
  "beacon.really_send": "本当に送信しますか?",
  "beacon.rigctld_on": "rigctld オン",
  "beacon.rigctld_off": "rigctld オフ",
  "beacon.preview": "プレビュー",
  "beacon.preview_empty": "プレビュー: この値ではまだパケットを作れません",
  "beacon.packet": "パケット",
  "beacon.packet_label": "送信されるビーコン",
  "beacon.status_label": "送信されるステータス",
};
