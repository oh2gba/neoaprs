import type { settings as en } from "@/i18n/en/settings";
import type { Message } from "@/i18n/message";

export const settings: Readonly<Record<keyof typeof en, Message>> = {
  "settings.none": "nessuno",
  "settings.default_placeholder": "(predefinito)",
  "settings.about": "Informazioni su {label}",
  "settings.saved": "Salvato",
  "settings.saving": "Salvataggio…",
  "settings.no_answer": "Nessuna risposta dal servizio.",
  "settings.not_sent": "Non inviato: non c’è connessione con il servizio.",
  "settings.no_word": "Ancora nessuna notizia dal servizio.",
  "settings.setup_again": "Ripeti la configurazione guidata",
  "settings.shorten_comment": "Prima accorcia il commento a {limit}",

  "settings.every_min": "Ogni {minutes} min",
  "settings.every_hours": { one: "Ogni {n} ora", other: "Ogni {n} ore" },

  "settings.group.station": "Stazione",
  "settings.group.tnc": "TNC",
  "settings.group.web": "Pagina web",
  "settings.group.notifications": "Notifiche",
  "settings.group.map": "Mappa",
  "settings.group.digi": "Digipeater",
  "settings.group.beacon": "Beacon",
  "settings.group.status": "Stato",
  "settings.group.other": "Altro",
  "settings.fold.antenna": "Antenna",
  "settings.fold.advanced": "Avanzate",

  "settings.name.position": "Posizione",
  "settings.name.tcp_address": "Indirizzo TCP",

  "settings.call.label": "Nominativo",
  "settings.lat.label": "Latitudine",
  "settings.lon.label": "Longitudine",
  "settings.symbol.label": "Simbolo",
  "settings.symbol_code.label": "Codice del simbolo",
  "settings.symbol.none": "Nessun simbolo",
  "settings.symbol.change": "Cambia",
  "settings.symbol.overlay": "Lettera o cifra sopra",

  "settings.comment.label": "Commento",
  "settings.comment.tip1":
    "Un breve testo inviato con la tua posizione in ogni beacon. Le altre stazioni lo vedono accanto al tuo nome sulla loro mappa. Lettere, cifre e normale punteggiatura, senza | né ~. Può essere lungo {max} caratteri, {with_phg} se è impostata la potenza.",
  "settings.comment.tip2": "Esempio: Stazione fissa, 2 m FM",

  "settings.station_status.name": "Testo di stato",
  "settings.station_status.label": "Testo",
  "settings.station_status.tip1":
    "Una riga su ciò che stai facendo, inviata a parte e non con ogni beacon. Le altre stazioni la vedono come il tuo stato. Viene inviata quando è nuova e dall’ultimo stato è trascorso l’intervallo Ogni. Fino a {max} caratteri, senza | né ~.",
  "settings.station_status.tip2": "Esempio: Alla casa in montagna, QRV 145.500 FM",

  "settings.power.label": "Potenza",
  "settings.power.tip1":
    "La potenza di uscita del trasmettitore. Insieme ad altezza, guadagno e direzione dell’antenna aggiunge al beacon un breve codice (PHG) che dice agli altri fin dove puoi essere ascoltato. Lascialo vuoto per non inviare nessuno dei quattro.",
  "settings.power.tip2": "Esempio: 5",

  "settings.antenna_height.label": "Altezza dell’antenna",
  "settings.antenna_height.tip1":
    "A quale altezza si trova l’antenna rispetto al terreno medio circostante, non rispetto al mare. Serve solo per il codice PHG.",
  "settings.antenna_height.tip2": "Esempio: 10 per un palo su una casa in terreno pianeggiante",

  "settings.antenna_gain.label": "Guadagno dell’antenna",
  "settings.antenna_gain.tip1": "Quanto l’antenna concentra il segnale, da {min} a {max} dB. Metti 0 se non lo sai. Serve solo per il codice PHG.",
  "settings.antenna_gain.tip2": "Esempio: 3",

  "settings.antenna_direction.label": "Direzione dell’antenna",
  "settings.antenna_direction.omni": "omni",
  "settings.antenna_direction.tip1":
    "Verso dove l’antenna favorisce il segnale: omni se funziona allo stesso modo in ogni direzione, come la maggior parte delle verticali e delle fruste, oppure il punto cardinale verso cui punta un’antenna direttiva. Serve solo per il codice PHG.",

  "settings.profile.label": "Tipo di radio",
  "settings.profile.tip_label": "Quale tipo di radio scegliere",
  "settings.profile.tip1":
    "Dice a NeoAPRS come parlare con la tua radio o il tuo modem (il suo TNC, la parte che trasforma il suono in pacchetti). Scegli la riga che corrisponde alla tua.",
  "settings.profile.tip2": "TNC KISS: Mobilinkd, NinoTNC, TNC-Pi e i Kenwood TH-D74 e TH-D75 con KISS attivato sulla radio. La scelta abituale.",
  "settings.profile.tip3":
    "KISS su TCP: Direwolf o un modem a scheda audio che gira su questo o su un altro computer. Anche un Digirig o un SignaLink passano da qui.",
  "settings.profile.tip4":
    "Kenwood TH-D7, TM-D700, TS-2000: NeoAPRS mette la radio in KISS da solo. Vale anche per il TM-D710 e il TH-D72, e per il Kantronics KPC-3+.",
  "settings.profile.tip5": "Non sei sicuro? Vedi la guida alle radio, docs/RADIOS.md.",

  "settings.port.name": "Porta del TNC",
  "settings.port.label": "Porta",
  "settings.port.tip_label": "Informazioni sulla porta",
  "settings.port.tip1":
    "Il collegamento con la radio. Su Linux, automatico significa che NeoAPRS ascolta le porte USB finché trova la radio, e la ricorda. Scegli tu la porta se hai più dispositivi o se la ricerca sceglie quella sbagliata.",
  "settings.port.tip2":
    "Una radio USB è /dev/ttyUSB0 su Linux e COM3 su Windows. Una radio Bluetooth compare in questo elenco dopo averla associata al computer.",
  "settings.port.tip3": "Aggiorna rilegge l’elenco, per esempio dopo aver collegato il cavo.",
  "settings.port.auto": "trova automaticamente",
  "settings.port.none": "nessuna scelta",
  "settings.port.other": "Altra...",
  "settings.port.path_label": "Percorso della porta",
  "settings.port.found": "trovata: {port}",
  "settings.port.refresh": "Aggiorna",

  "settings.baud.name": "Velocità del TNC",
  "settings.baud.label": "Velocità",
  "settings.baud.tip_label": "Informazioni sulla velocità",
  "settings.baud.tip1":
    "La velocità del cavo tra il computer e il TNC. Lasciala vuota: NeoAPRS usa allora la velocità del TNC che hai scelto, 9600 per la maggior parte.",
  "settings.baud.tip2":
    "Impostala solo se il manuale del tuo TNC lo dice, per esempio 57600 per un NinoTNC. Le connessioni Bluetooth e TCP non hanno velocità.",

  "settings.tcp_host.label": "Host TCP",
  "settings.tcp_port.label": "Porta TCP",
  "settings.tcp_port.title": "Direwolf 8001, soundmodem 8100",
  "settings.last_port.label": "Ultima porta trovata",
  "settings.pattern.label": "Porte da cercare",
  "settings.pattern.title": "Modelli di dispositivo, separati da spazi",
  "settings.skip.label": "Porte da saltare",
  "settings.skip.title": "Percorsi di dispositivo, separati da virgole",

  "settings.network.name": "Accesso dalla rete",
  "settings.network.label": "Consenti l’accesso dalla rete",
  "settings.network.tip_label": "Informazioni sull’accesso dalla rete",
  "settings.network.tip1":
    "Permette ad altri dispositivi della tua rete di aprire questa pagina: un portatile, un telefono o un tablet. Senza, solo il computer su cui gira NeoAPRS può aprirla.",
  "settings.network.tip2":
    "Impostalo su sì e premi Salva: compare una chiave di accesso con gli indirizzi da aprire. Digita la chiave una volta su ogni dispositivo.",
  "settings.network.tip3":
    "La connessione è http in chiaro sulla tua rete di casa: va bene in casa, non per internet. Non aprire nel router una porta verso NeoAPRS.",

  "settings.access_key.label": "Chiave di accesso",
  "settings.access_key.tip_label": "Informazioni sulla chiave di accesso",
  "settings.access_key.tip1":
    "La password per gli altri dispositivi. Apri uno degli indirizzi qui sotto sul portatile o sul telefono e digita questa chiave una volta; il dispositivo resta connesso.",
  "settings.access_key.tip2": "Nuova chiave ne crea un’altra e disconnette tutti gli altri dispositivi. Digita di nuovo la nuova chiave su ciascuno.",
  "settings.new_key": "Nuova chiave",
  "settings.new_key_sure": "sicuro?",
  "settings.urls.label": "Apri su",
  "settings.urls.tip_label": "Informazioni sugli indirizzi",
  "settings.urls.tip1": "Digita uno di questi nel browser del portatile o del telefono, che deve essere nella stessa rete di NeoAPRS.",
  "settings.urls.tip2":
    "Quello con i numeri funziona ovunque nella rete. Quello che finisce in .local è più facile da ricordare e funziona sulla maggior parte di telefoni e portatili.",
  "settings.key_screen.label": "Chiave di accesso",
  "settings.key_screen.placeholder": "xxxx-xxxx-xxxx",
  "settings.key_screen.open": "Apri",
  "settings.access.wrong": "Chiave errata.",
  "settings.access.shut_out": "Troppi tentativi. Attendi qualche minuto.",

  "settings.https.name": "Connessione sicura",
  "settings.https.label": "Connessione sicura (https)",
  "settings.https.tip_label": "Informazioni sulla connessione sicura",
  "settings.https.tip1":
    "Serve per le notifiche sui telefoni e per installare NeoAPRS come app. I browser mostrano un avviso la prima volta; puoi proseguire comunque, oppure installare il certificato di NeoAPRS su ogni dispositivo per far sparire l’avviso.",

  "settings.radius.name": "Raggio della mappa",
  "settings.radius.label": "Raggio",
  "settings.radius.tip_label": "Informazioni sul raggio",
  "settings.radius.tip1":
    "Fin dove arriva la mappa dettagliata dalla tua stazione, in ogni direzione. La mappa del mondo c’è sempre; questa è la zona con strade e nomi.",
  "settings.radius.tip2":
    "Un raggio maggiore significa un download maggiore: 150 km sono una regione, 500 km buona parte di un paese. La dimensione è mostrata prima di iniziare.",

  "settings.digipeater.label": "Digipeater",
  "settings.digipeater.tip_label": "Cosa fa il digipeater",
  "settings.digipeater.tip1":
    "Aiuta le stazioni vicine che non raggiungono un digipeater: i pacchetti che chiedono WIDE1-1, o che passano dal tuo nominativo, vengono ripetuti una volta dalla tua radio.",
  "settings.digipeater.tip2": "Lascialo spento a meno che tu non sia in un posto con scarsa copertura.",

  "settings.alert.label": "Avviso",
  "settings.alert_command.name": "Comando di avviso",
  "settings.alert_command.label": "Comando",
  "settings.alert_test": "Prova",
  "settings.alerts.text": "Sul computer di NeoAPRS",
  "settings.alerts.title": "L’avviso di NeoAPRS stesso: il comando che il servizio esegue sul computer su cui gira",
  "settings.alerts.tip_label": "Informazioni sugli avvisi",
  "settings.alerts.tip1":
    "Un nuovo messaggio può avvisarti in due posti. Questo gruppo è il computer di NeoAPRS stesso: con l’avviso attivo, esegue il Comando all’arrivo di un messaggio, di norma una notifica e un suono. Se NeoAPRS gira su un altro computer, suona lì.",
  "settings.alerts.tip2":
    "Il gruppo successivo è questo browser, sul dispositivo che ha la pagina aperta: nessun avviso, un suono, un suono e una notifica, oppure solo una notifica. Ogni dispositivo sceglie per sé, e Prova suono e Prova notifica lo mettono alla prova.",
  "settings.alerts.tip3": "Se leggi NeoAPRS sul computer su cui gira, ne basta uno dei due; usali entrambi solo se vuoi essere avvisato due volte.",

  "settings.browser.heading": "In questo browser",
  "settings.browser.mode": "Avviso per un nuovo messaggio",
  "settings.browser.enable_popups": "Attiva le notifiche…",
  "settings.browser.sound": "Suono",
  "settings.browser.test_sound": "Prova suono",
  "settings.browser.popup": "Notifica",
  "settings.browser.test_popup": "Prova notifica",
  "settings.alert_mode.off": "nessuno",
  "settings.alert_mode.sound": "suono",
  "settings.alert_mode.both": "suono e notifica",
  "settings.alert_mode.popup": "solo notifica",
  "settings.alert_mode.why_off": "Le notifiche sono disattivate in questo browser per questo indirizzo",
  "settings.alert_mode.why_blocked": "Le notifiche sono bloccate per questa pagina nel browser",
  "settings.alert.notification_title": "Messaggio APRS da {call}",
  "settings.alert.test_message": "Questa è una prova dell’avviso di NeoAPRS",
  "settings.alert.note_refused": "notifiche rifiutate: solo suono",
  "settings.alert.note_blocked": "notifiche bloccate",
  "settings.alert.note_not_yet": "notifiche non ancora consentite",
  "settings.alert.sound_played": "riprodotto",
  "settings.alert.sound_locked": "suono bloccato: clicca una volta sulla pagina",
  "settings.alert.popup_off": "le notifiche sono disattivate per questo indirizzo",
  "settings.alert.popup_blocked": "notifica bloccata",
  "settings.alert.popup_sent": "notifica inviata",

  "settings.status_source.label": "Stato",
  "settings.status_source.off": "spento",
  "settings.status_source.text": "un testo mio",
  "settings.status_source.rig": "la frequenza della mia radio (rigctld)",
  "settings.status_source.tip1":
    "Uno stato è una riga che le altre stazioni vedono con il tuo nome. Spento non ne invia nessuno. Un testo mio invia la riga che scrivi. La frequenza della mia radio chiede alla tua radio, tramite rigctld, su cosa è sintonizzata e invia quello.",
  "settings.status_rigctld.label": "Rigctld",
  "settings.status_rigctld.tip1":
    "rigctld è un piccolo programma di Hamlib che permette a un computer di chiedere a una radio su cosa è sintonizzata; avvialo prima per la tua radio. Scrivi dove ascolta, come indirizzo:porta. 4532 è la porta abituale.",
  "settings.status_rigctld.tip2": "Esempio: 127.0.0.1:4532",
  "settings.status_interval.name": "Intervallo dello stato",
  "settings.status_interval.label": "Ogni",
  "settings.status_interval.tip1":
    "Il tempo minimo tra due rapporti di stato. Uno stato non viene inviato di nuovo finché dice la stessa cosa dell’ultimo, per quanto tempo sia passato; da 30 minuti a 2 ore vanno bene per uno stato che dice cosa stai facendo o su cosa è sintonizzata la radio.",
  "settings.status_template.name": "Modello dello stato",
  "settings.status_template.label": "Testo",
  "settings.status_template.tip1":
    "Lo stato è composto da questo testo con ciò su cui la tua radio è sintonizzata ora: {{freq}} diventa la frequenza e {{mode}} il modo. Fino a {max} caratteri una volta compilati.",
  "settings.status_template.tip2": "Esempio: QRV {{freq}} {{mode}} dà QRV 14.074 MHz USB",

  "settings.beacon_interval.name": "Intervallo del beacon",
  "settings.beacon_interval.label": "Beacon",
  "settings.beacon_interval.off": "Spento",
  "settings.beacon_interval.tip1":
    "Ogni quanto viene inviata la tua posizione. Spento non ne invia da solo; Invia beacon ora ne invia comunque uno. Ogni beacon occupa il canale per tutti i vicini, quindi 30 minuti è una buona scelta per una stazione che resta ferma; {min} è il minimo.",
  "settings.path.name": "Percorso del beacon",
  "settings.path.label": "Percorso",
  "settings.path.recommended": "Consigliato ({path})",
  "settings.path.direct": "Solo diretto (senza digipeater)",
  "settings.path.custom": "Personalizzato…",
  "settings.path.custom_label": "Digipeater",
  "settings.path.tip1":
    "Il percorso consigliato segue il simbolo della tua stazione: una stazione in movimento (auto, bici, barca, aereo) usa WIDE1-1,WIDE2-1, così un piccolo digipeater vicino raccoglie prima il pacchetto e uno ad ampia copertura lo porta oltre. Qualsiasi altro simbolo è una stazione fissa, che raggiunge direttamente un digipeater ad ampia copertura e le basta WIDE2-1.",
  "settings.path.tip2":
    "Scegli Solo diretto se tutti quelli con cui parli ti sentono direttamente. I messaggi scelgono da soli il percorso, a meno che tu non ne imposti uno per la stazione.",

  "settings.confirm.label": "Conferma",
  "settings.confirm.yes": "Sì",
  "settings.confirm.cancel": "Annulla",
  "settings.confirm.network_off": "Questo dispositivo perderà la pagina. Disattivare?",
  "settings.confirm.https_on": "Questo dispositivo perderà la pagina. Attivare?",
  "settings.confirm.https_off": "Questo dispositivo perderà la pagina. Disattivare?",

  "settings.undo.changed": "{name} modificato",
  "settings.undo.undo": "Annulla",

  "settings.check.range": "Da {min} a {max}",
  "settings.check.placeholder_call": "{call} non è un nominativo",
  "settings.check.not_call": "Non è un nominativo",
  "settings.check.not_number": "Non è un numero",
  "settings.check.between": "Tra -{limit} e {limit}",
  "settings.check.symbol_length": "Tabella e codice",
  "settings.check.symbol_table": "Tabella: / \\ 0-9 A-Z",
  "settings.check.symbol_code": "Codice: un carattere stampabile",
  "settings.check.not_address": "Non è un indirizzo",
  "settings.check.path": "Nominativi separati da virgole, al massimo {max}",
  "settings.check.needs_latitude": "Serve insieme alla latitudine",
  "settings.check.needs_longitude": "Serve insieme alla longitudine",

  "settings.location.heading": "Posizione",
  "settings.location.pick": "Scegli sulla mappa",
  "settings.location.cancel": "Annulla",
  "settings.location.not_set": "Non impostata",
  "settings.location.enter": "Inserisci le coordinate",

  "settings.picker.title": "Scegli un simbolo",
  "settings.picker.placeholder": "Cerca: casa, auto, digi, wx...",
  "settings.picker.search": "Cerca simboli",
  "settings.picker.close": "Chiudi",
  "settings.picker.usual": "Abituali",
  "settings.picker.usual_symbols": "Simboli abituali",
  "settings.picker.all": "Tutti",
  "settings.picker.all_symbols": "Tutti i simboli",
  "settings.picker.none": "Nessun simbolo del genere.",

  "settings.tnc.state.stopped": "fermo",
  "settings.tnc.state.connecting": "connessione",
  "settings.tnc.state.connected": "connesso",
  "settings.tnc.state.waiting": "in attesa",
  "settings.tnc.state.silent": "silenzioso",
  "settings.tnc.no_packet": "Ancora nessun pacchetto",
  "settings.tnc.last_packet": "Ultimo pacchetto {span} fa",
  "settings.tnc.no_packet_digipeated": "Ancora nessun pacchetto, ripetuti {count}",
  "settings.tnc.last_packet_digipeated": "Ultimo pacchetto {span} fa, ripetuti {count}",
  "settings.tnc.searching": "Ricerca della radio…",
  "settings.tnc.connecting": "Connessione…",
  "settings.tnc.connecting_to": "Connessione a {path}…",
  "settings.tnc.not_connected": "Non connesso",
  "settings.tnc.not_connected_why": "Non connesso: {why}",
  "settings.tnc.counts": {
    one: "{n} pacchetto ricevuto, {bytes_in} rx, {bytes_out} tx, {digipeated} ripetuti",
    other: "{n} pacchetti ricevuti, {bytes_in} rx, {bytes_out} tx, {digipeated} ripetuti",
  },
  "settings.tnc.reconnect": "Riconnetti",
  "settings.tnc.ports": "Porte",
  "settings.tnc.terminal": "Terminale",
  "settings.tnc.terminal_label": "Cosa il TNC ha visto e fatto",

  "settings.map.step.tool": "Recupero del programma pmtiles",
  "settings.map.step.build": "Ricerca dell’ultima versione",
  "settings.map.step.world": "Mappa del mondo",
  "settings.map.step.area": "Mappa della zona",
  "settings.map.estimating": "Stima",
  "settings.map.working": "In corso",
  "settings.map.step_percent": "{step} {percent}%",
  "settings.map.downloaded": "Mappa scaricata",
  "settings.map.downloaded_on": "Mappa scaricata il {day} {month}",
  "settings.map.checking": "Controllo della dimensione…",
  "settings.map.download_size": "Scaricare {size}?",
  "settings.map.downloading": "Download…",
  "settings.map.download_again": "Scarica di nuovo la mappa",
  "settings.map.download": "Scarica mappa",
  "settings.map.cancel": "Annulla",

  "settings.update.group": "Controllo aggiornamenti",
  "settings.update.label": "Nuova versione",
  "settings.update.check": "Controlla ora",
  "settings.update.tip_label": "Informazioni sul controllo aggiornamenti",
  "settings.update.tip":
    "Una volta al giorno NeoAPRS chiede alla pagina delle versioni del progetto se ne è uscita una più recente, e te lo dice nel piè di pagina.",
  "settings.update.available": "{version} disponibile",
  "settings.update.current": "aggiornato ({version})",
  "settings.update.no_answer": "nessuna risposta",
};
