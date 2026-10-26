// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { shell as source } from "@/i18n/en/shell";
import type { Message } from "@/i18n/message";

export const shell: Record<keyof typeof source, Message> = {
  "common.dismiss": "閉じる",

  "header.project_title": "NeoAPRSプロジェクトのページ",
  "pill.rx": "RX only",
  "pill.rx_title": "何も送信しません。設定 → 無線機 → RX only",
  "pill.beacon_off": "ビーコン停止",
  "pill.beacon_off_title": "自動のビーコンとステータスは送りません。ビーコンタブ",
  "pill.internet": "Internet",
  "pill.internet_title": "インターネット:APRS-ISの局を地図に表示。設定 → インターネットの局",
  "pill.gps": "GPS",
  "pill.gps_fix_title": "GPS:測位済み。ビーコンタブ",
  "pill.gps_nofix_title": "GPS:まだ測位していません。ビーコンタブ",
  "pill.rx_send": "RX only:何も送信しません",
  "header.no_call": "コールサイン未設定",
  "header.no_call_title": "コールサインを設定するまで何も送信されません。設定を開きます",
  "header.unread_open": {
    other: "未読メッセージが{n}件あります。メッセージを開きます",
  },

  "unread.not_seen": { other: "未読メッセージ{n}件" },
  "unread.new_bulletins": { other: "新しい掲示{n}件" },

  "tab.messages": "メッセージ",
  "tab.stations": "局",
  "tab.nearby": "周辺",
  "tab.email": "メール",
  "tab.bulletins": "掲示",
  "tab.objects": "オブジェクト",
  "tab.beacon": "ビーコン",
  "tab.packets": "パケット",
  "tab.settings": "設定",
  "tab.more": "その他",
  "tab.menu_new": "、新着{n}件",

  "panel.label": "詳細",
  "panel.map": "地図",
  "panel.width": "パネルの幅",
  "panel.show": "パネルを表示",
  "panel.hide": "パネルを隠す",
  "panel.show_unseen": "パネルを表示、{unseen}",

  "footer.cost": "NeoAPRSはプロセッサコア1つの{cpu} %と{mb} MBのメモリを使用しています。稼働時間: {span}",
  "footer.cost_no_memory": "NeoAPRSはプロセッサコア1つの{cpu} %を使用しています。稼働時間: {span}",
  "footer.update": "{version}に更新",
  "footer.offline": "デーモンに接続できません",
  "footer.connecting": "接続中…",
  "footer.radio.waiting": "無線機: 待機中…",
  "footer.radio.waiting_title": "TNCからまだ応答がありません",
  "footer.radio.silent": "無線機: 受信なし",
  "footer.radio.entering_kiss": "無線機: KISSモードに移行中…",
  "footer.radio.searching": "無線機: 検索中…",
  "footer.radio.not_connected": "無線機: 未接続",
  "footer.radio.open_settings": "無線機の設定を開く",

  "mismatch.notice":
    "このページと NeoAPRS が一致しません（ページ {page}、NeoAPRS {neoaprs}）。ページを再読み込みしてください。変わらない場合は NeoAPRS を再起動してください。",
  "mismatch.reload": "再読み込み",

  "settings.language.label": "言語",
  "settings.language.tip1": "このページの言語です。ブラウザーやデバイスごとに選択が記憶されます。",
};
