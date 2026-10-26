import type { shell as en } from "@/i18n/en/shell";
import type { Message } from "@/i18n/message";

export const shell: Readonly<Record<keyof typeof en, Message>> = {
  "common.dismiss": "Descartar",

  "header.project_title": "La página del proyecto NeoAPRS",
  "header.receive_only": "Solo recepción",
  "header.receive_only_title":
    "No se transmite nada: esta estación está en solo recepción. Es el ajuste station/transmit del servicio, que no está en esta página; neoaprs db set station/transmit true lo cambia en el próximo inicio",
  "header.no_call": "sin indicativo",
  "header.no_call_title": "No se transmite nada hasta que se fije un indicativo: abrir el asistente de configuración",
  "header.unread_open": {
    one: "{n} mensaje sin ver: abrir los mensajes",
    other: "{n} mensajes sin ver: abrir los mensajes",
  },

  "unread.not_seen": { one: "{n} mensaje sin ver", other: "{n} mensajes sin ver" },
  "unread.new_bulletins": { one: "{n} boletín nuevo", other: "{n} boletines nuevos" },

  "tab.messages": "Mensajes",
  "tab.stations": "Estaciones",
  "tab.nearby": "Cerca",
  "tab.email": "Correo",
  "tab.bulletins": "Boletines",
  "tab.objects": "Objetos",
  "tab.beacon": "Baliza",
  "tab.packets": "Paquetes",
  "tab.settings": "Ajustes",
  "tab.menu_new": ", nuevos: {n}",

  "panel.label": "Detalles",
  "panel.map": "Mapa",
  "panel.width": "Ancho del panel",
  "panel.show": "Mostrar el panel",
  "panel.hide": "Ocultar el panel",
  "panel.show_unseen": "Mostrar el panel, {unseen}",

  "footer.cost": "NeoAPRS usa el {cpu} % de un núcleo del procesador y {mb} MB de memoria, y lleva {span} en marcha",
  "footer.cost_no_memory": "NeoAPRS usa el {cpu} % de un núcleo del procesador y lleva {span} en marcha",
  "footer.update": "Actualizar a {version}",
  "footer.offline": "Servicio sin conexión",
  "footer.connecting": "Conectando…",
  "footer.radio.waiting": "Radio: esperando…",
  "footer.radio.waiting_title": "aún sin noticias del TNC",
  "footer.radio.silent": "Radio: en silencio",
  "footer.radio.entering_kiss": "Radio: entrando en KISS…",
  "footer.radio.searching": "Radio: buscando…",
  "footer.radio.not_connected": "Radio: sin conexión",
  "footer.radio.open_settings": "Abrir los ajustes de la radio",

  "settings.language.label": "Idioma",
  "settings.language.tip1": "El idioma de esta página. Cada navegador y dispositivo recuerda el suyo.",
};
