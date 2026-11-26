// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { layersettings as source } from "@/i18n/en/layersettings";
import type { Message } from "@/i18n/message";

export const layersettings: Record<keyof typeof source, Message> = {
  "layers.settings.none": "なし",
  "layers.settings.source": "情報源",
  "layers.settings.aircraft_tip_label": "航空機について",
  "layers.settings.aircraft_tip1": "航空機の情報源です。インターネット上のサービスか、自分の受信機です。",
  "layers.settings.aircraft_tip2": "レイヤーの箱で航空機にチェックを入れると、地図に航空機が表示されます。",
  "layers.settings.ships_tip_label": "船舶について",
  "layers.settings.ships_tip1":
    "Fintraffic はフィンランドの海域をカバーし、地図がその海域に届く場合だけ表示されます。自分の受信機も使えます。",
  "layers.settings.ships_tip2": "レイヤーの箱で船舶にチェックを入れると、地図に船舶が表示されます。",
  "layers.receiver.own": "自分の受信機",
  "layers.receiver.address": "受信機のアドレス",
  "layers.receiver.empty": "このコンピューター",
  "layers.receiver.radarcape_tip": "ネットワーク上のRadarcapeのアドレスです。",
  "layers.receiver.aircraft_tip_label": "受信機のアドレスについて",
  "layers.receiver.aircraft_tip1":
    "readsb、dump1090、tar1090、PiAware のいずれかが動いている受信機(たとえば Raspberry Pi)です。名前、番号、またはWebアドレスを入力します。",
  "layers.receiver.aircraft_tip2": "受信機がこのコンピューターで動いている場合は空のままにします。",
  "layers.receiver.ships_tip_label": "受信機のアドレスについて",
  "layers.receiver.ships_tip1": "受信機の船舶メッセージを送ってくるコンピューターの名前です。",
  "layers.receiver.ships_tip2": "受信機がこのコンピューターで動いている場合は空のままにします。",
  "layers.receiver.state.looking": "探索中",
  "layers.receiver.state.receiving": "受信中",
  "layers.receiver.state.no_answer": "応答なし",
  "layers.receiver.line.looking": "受信機を探しています",
  "layers.receiver.line.no_answer": "受信機から応答がありません",
  "layers.receiver.state.no_ais": "AISなし",
  "layers.receiver.line.no_ais": "接続済みですが、AISが届きません",
  "layers.receiver.line.aircraft": { other: "受信中: 航空機 {n} 機、{span}前" },
  "layers.receiver.line.aircraft_none": "受信中、航空機はまだありません",
  "layers.receiver.line.ships": { other: "受信中: 船舶 {n} 隻、{span}前" },
  "layers.receiver.line.ships_none": "接続済み、船舶はまだ受信していません",
};
