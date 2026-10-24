// This translation has not yet been reviewed by a native-speaking ham; corrections are welcome.
import type { shell as source } from "@/i18n/en/shell";
import type { Message } from "@/i18n/message";

export const shell: Record<keyof typeof source, Message> = {
  "common.dismiss": "Dispensar",

  "header.project_title": "A página do projeto NeoAPRS",
  "header.no_call": "indicativo não definido",
  "header.no_call_title": "Nada é transmitido enquanto não houver um indicativo: abra a configuração",
  "header.unread_open": {
    one: "{n} mensagem não vista: abrir as mensagens",
    other: "{n} mensagens não vistas: abrir as mensagens",
  },

  "unread.not_seen": { one: "{n} mensagem não vista", other: "{n} mensagens não vistas" },
  "unread.new_bulletins": { one: "{n} boletim novo", other: "{n} boletins novos" },

  "tab.messages": "Mensagens",
  "tab.stations": "Estações",
  "tab.email": "E-mail",
  "tab.bulletins": "Boletins",
  "tab.objects": "Objetos",
  "tab.beacon": "Beacon",
  "tab.packets": "Pacotes",
  "tab.settings": "Ajustes",
  "tab.menu_new": ", novidades: {n}",

  "panel.label": "Detalhes",
  "panel.map": "Mapa",
  "panel.width": "Largura do painel",
  "panel.show": "Mostrar o painel",
  "panel.hide": "Ocultar o painel",
  "panel.show_unseen": "Mostrar o painel, {unseen}",

  "footer.cost": "O NeoAPRS usa {cpu} % de um núcleo do processador e {mb} MB de memória, em execução há {span}",
  "footer.cost_no_memory": "O NeoAPRS usa {cpu} % de um núcleo do processador, em execução há {span}",
  "footer.update": "Atualizar para {version}",
  "footer.offline": "Daemon offline",
  "footer.connecting": "Conectando…",
  "footer.radio.waiting": "Rádio: aguardando…",
  "footer.radio.waiting_title": "o TNC ainda não deu sinal",
  "footer.radio.silent": "Rádio: em silêncio",
  "footer.radio.entering_kiss": "Rádio: entrando em KISS…",
  "footer.radio.searching": "Rádio: procurando…",
  "footer.radio.not_connected": "Rádio: não conectado",
  "footer.radio.open_settings": "Abrir os ajustes do rádio",

  "settings.language.label": "Idioma",
};
