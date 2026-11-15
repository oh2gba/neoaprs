// The Radio group of the Settings tab with any number of radios (the round's package U2): the words of a radio's box, of adding and removing a radio, of the main radio, and the radio types' names. The shared words of the
// radios (`radio.*`) are spelled as the round's plan has them; the integration joins this file into the areas and takes out the words another package also gives.
export const u2 = {
  "radio.add": "Add radio",
  "radio.add_button": "Add",
  "radio.remove": "Remove",
  "radio.remove_sure": "Really remove?",
  "radio.main": "Main radio",
  "radio.main.tip_label": "About the main radio",
  "radio.main.tip1": "Bulletins and the status go out on it, and it is the first choice for Ask around, Local info and email.",
  "radio.name": "Name",
  "radio.name.tip_label": "About the name",
  "radio.name.tip1": "A short name for this radio: the page calls the radio by it everywhere.",
  "radio.line": "{name}: {line}",
  "settings.group.lora_radio": "LoRa radio",

  "radio.type.kenwood_tnc2": "Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2",
  "radio.type.kenwood_d710": "Kenwood TM-D710 / TH-D72",
  "radio.type.kantronics": "Kantronics KPC-3+",
  "radio.type.kiss": "KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)",
  "radio.type.kiss_tcp": "KISS over TCP (Direwolf, soundmodem)",
  "radio.type.dummy": "Dummy (no radio, made-up traffic)",
  "radio.type.mercury": "Mercury HF modem (sound card, SSB radio)",
  "radio.type.dummy_hf": "Dummy HF radio (no radio, made-up distant stations)",
} as const;
