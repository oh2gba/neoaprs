import type { layersettings as en } from "@/i18n/en/layersettings";
import type { Message } from "@/i18n/message";

export const layersettings: Readonly<Record<keyof typeof en, Message>> = {
  "layers.settings.none": "Nenhuma",
  "layers.settings.source": "Fonte",
  "layers.settings.aircraft_tip_label": "Sobre as aeronaves",
  "layers.settings.aircraft_tip1": "De onde vêm as aeronaves: um serviço na internet ou um receptor seu.",
  "layers.settings.aircraft_tip2": "As aeronaves aparecem no mapa quando Aeronaves está marcado na caixa Camadas.",
  "layers.settings.ships_tip_label": "Sobre os navios",
  "layers.settings.ships_tip1":
    "A Fintraffic cobre as águas da Finlândia e só aparece onde seu mapa chega a elas. Ou use um receptor seu.",
  "layers.settings.ships_tip2": "Os navios aparecem no mapa quando Navios está marcado na caixa Camadas.",
  "layers.receiver.own": "Meu próprio receptor",
  "layers.receiver.address": "Endereço do receptor",
  "layers.receiver.empty": "Este computador",
  "layers.receiver.radarcape_tip": "O endereço do seu Radarcape na sua rede.",
  "layers.receiver.aircraft_tip_label": "Sobre o endereço do receptor",
  "layers.receiver.aircraft_tip1":
    "Um receptor com readsb, dump1090, tar1090 ou PiAware, por exemplo num Raspberry Pi. Digite o nome, o número ou o endereço web dele.",
  "layers.receiver.aircraft_tip2": "Deixe vazio quando o receptor roda neste computador.",
  "layers.receiver.ships_tip_label": "Sobre o endereço do receptor",
  "layers.receiver.ships_tip1": "O nome do computador que envia as mensagens de navios do seu receptor.",
  "layers.receiver.ships_tip2": "Deixe vazio quando o receptor roda neste computador.",
  "layers.receiver.state.looking": "procurando",
  "layers.receiver.state.receiving": "recebendo",
  "layers.receiver.state.no_answer": "sem resposta",
  "layers.receiver.line.looking": "Procurando o receptor",
  "layers.receiver.line.no_answer": "Sem resposta do receptor",
  "layers.receiver.line.aircraft": {
    one: "Recebendo: {n} aeronave, há {span}",
    other: "Recebendo: {n} aeronaves, há {span}",
  },
  "layers.receiver.line.aircraft_none": "Recebendo, nenhuma aeronave ainda",
  "layers.receiver.line.ships": { one: "Recebendo: {n} navio, há {span}", other: "Recebendo: {n} navios, há {span}" },
  "layers.receiver.line.ships_none": "Conectado, nenhum navio ouvido ainda",
};
