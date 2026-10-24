// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { email as source } from "@/i18n/en/email";
import type { Message } from "@/i18n/message";

export const email: Record<keyof typeof source, Message> = {
  "email.compose": "メール",
  "email.to": "宛先 {address}",
  "email.from": "差出人 {address}",
  "email.checked": "メールを確認しました",

  "email.none": "メールはまだありません。",
  "email.list": "メール",
  "email.delete": "削除: {title}",

  "email.check": "メールを確認",
  "email.checking": "確認中です",
  "email.about": "メールについて",
  "email.about_gateway": "メールはインターネットゲートウェイ EMAIL-2 にiGate経由で届くため、着信していても「{unconfirmed}」と表示されることがあります。",
  "email.about_check": "「{check}」は、ゲートウェイがあなた宛てに預かっているメールを問い合わせます(預かるのは24時間です)。",

  "email.field.to": "宛先",
  "email.field.address": "メールアドレス",
  "email.field.text": "本文",
  "email.used_before": "過去に使用",
  "email.forget": "{address}を削除",
  "email.send": "送信",

  "email.state.waiting": "無線機を待っています",
  "email.state.sending": "送信中({attempt}/{max})",
  "email.state.delivered": "配信済み",
  "email.state.rejected": "拒否",
  "email.state.cancelled": "キャンセル",
  "email.state.unconfirmed": "未確認",
  "email.not_confirmed": "送信済み、未確認: ゲートウェイの応答確認はiGate経由でしか届かないため、メールは届いている可能性があります",

  "email.date_time": "{month}{day}日 {time}",
};
