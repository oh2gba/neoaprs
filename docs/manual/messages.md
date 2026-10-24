# Messages

The Messages tab sends APRS text messages to other stations and shows the ones sent to you, as conversations, one for each other call. Every message is kept in the database, so a restart goes on where the daemon stopped.

Messages to bulletins and groups belong to the [message board](bulletins.md), and mail to the [email gateway](email.md) has its own tab. A first message on the air is not tried by NeoAPRS's tests: check it live with a station that answers, and look at the Packets tab for the message, the ack and the repeats.

## Sending

The addressee is a call with an optional SSID, written in upper case. Your own call is refused (the base call of yours with another SSID is another station).

The text is at most 67 characters of printable ASCII, the specification's text. A letter with an accent is refused, because the radios that read it would show it wrongly. The text has no `|`, `~`, `{` or control character, and does not begin like an ack or a reject (`ack12`). A refusal names the reason.

The message gets the next message id: two characters, `01` to `99`, then `A0` to `ZZ`, `0A` to `9Z` and `00`, 1296 in all, one after the other, skipping the ids of messages still being sent. It goes out at once as a packet from your call to `APZNEO` by the digipeaters of the station's path (below). The text is followed by `{` and the id and `}`; the braces say that you know reply-acks (below). With the defaults your first message, "Hello Pekka" to OH2RDG, is:

```
OH2GBA>APZNEO,WIDE2-1::OH2RDG   :Hello Pekka{01}
```

A message to a bulletin or a group (`BLN0` to `BLNZ`, `BLN3HAMS`, `ALL`, `CQ`, `QST`, `NWS-xxxxx`, `SKY`, `CWA`) goes out once, without an id, and is never retried. It is kept as *unconfirmed* with one attempt.

A query that you ask from the menu of the Stations table (`?APRSP`, `?APRSS`, `?APRSD`, `?APRST`: see [Page](page.md)) is the same: a message to the station sent once, with no id, never retried, kept as *unconfirmed*. The thread shows it as a small grey line in the middle, "You asked for its status" and the time, and not as a bubble with the query in it. The answer is the station's own: a packet, or a message that is a bubble like any other. The same query to the same station is not sent twice within 60 seconds.

### Attempts

The same frame is sent again until the addressee answers: 4 times in all, and 2 times for the email gateway, because its acks rarely reach you. There is no setting for this. The waits double: the 4 attempts are made 0, 30, 60 and 120 seconds after the first, the 2 to the gateway at 0 and 30. The answer to the last attempt is waited for 240 seconds, then the message has *failed*. A message that was given only 1 or 2 attempts (the gateway's, a bulletin's) is *unconfirmed* instead, since no ack was expected.

An ack from the addressee that quotes your id makes the message *acked*. A reject makes it *rejected*. Either ends the attempts, and one that comes late still settles a message that has failed, is unconfirmed or was cancelled.

**Cancel** stops a message that is being sent. **Retry** sends a failed, unconfirmed, rejected or cancelled one again from the first attempt, with the same id.

While the TNC is not connected, an attempt that is due waits for it. None is used up, the waits that were running are moved on by the time the radio was away, and the log says so once. A message written then is kept and its first attempt goes out when the TNC is back. After a restart the schedule goes on from the latest attempt that was made.

### The pace

Your attempts, of any messages, go out one at a time, at least 10 seconds apart. The first goes at once. Messages written together, such as one text to several stations, wait their turn in the order they were written, in the state *sending* with no attempt used. The retries of different messages keep the pause too. Acks and answers to queries are not held back.

### Unconfirmed

Some stations never ack to you. The email gateway's acks reach you only if an iGate within reach puts them on the air, and a station that is not listening will never answer however often it is told. A message with 1 or 2 attempts that has used them without an ack is not a failure. It becomes *unconfirmed* (a hollow check on the page; the thread says "sent once, no ack" or "sent twice, no ack"). The cross is kept for a message that was given 3 attempts or more. An ack or a reject that comes later still settles it, and Retry sends it again.

## Receiving

A message is for you when its addressee is your call with its SSID, exactly. No SSID and `-0` are the same. With OH2GBA-7, a message to OH2GBA-7 is yours; those to OH2GBA and OH2GBA-9 are other stations'.

- A text that is a [query](beacon.md#answers-to-queries), or the definition of the channels of a telemetry station (it begins `PARM.`, `UNIT.`, `EQNS.` or `BITS.`), is neither kept nor acked, whatever id it carries. The Packets tab has it.
- Any other message is kept (direction in, from the packet's source). When it carries an id it is answered at once with an ack by the sender's path. For message 12 from OH2RDG-7: `OH2GBA>APZNEO,WIDE2-1::OH2RDG-7 :ack12`.
- A text that reads as an ack or a reject (`ack12`, `rej12`) is one only when it quotes the id of a message of yours to that station. Otherwise it is the words of a person ("rejoin", "ackbar"), kept as a message without an id and not acked.
- One ack goes out for each burst of copies. The first copy is acked at once. A further copy of the same message (same sender, id and text, such as a digipeater's copy or an iGate's) is acked again only when it arrives more than 10 seconds after your last ack of it, which is a sender that did not hear you and tries again. So three copies in six seconds cost one ack on the air.
- The same id and text from the same station within 30 minutes is a repeat and is kept once. After 31 minutes it is a new message and is acked at once, and so is a new text with an id that was used (a sender that began its numbering again).
- A message without an id is kept and not acked. A repeat of it within 30 minutes (the same sender, addressee and text, which is what two digipeaters' copies of an auto-reply look like) is not kept again.
- The time of your last ack of a message is held in memory, so after a restart the first copy is acked again.

### Reply-acks

An ack that has to cross several hops is the likeliest frame to be lost. So, following WB4APR's reply-ack addendum, a message may carry an ack for the other station's latest message in its own number: `{MM}AA`, where `MM` is its id and `AA` the id of a message of the other station. `{MM}` alone says that the sender knows the form.

Every message you send has the number in that form, and the normal ack frames go out too: the reply-ack is extra. With the defaults, a message 05 from OH2RDG that said `{05}` and your answer to it, message 01:

```
OH2GBA>APZNEO,WIDE2-1::OH2RDG   :ack05
OH2GBA>APZNEO,WIDE2-1::OH2RDG   :Moikka{01}05
```

- Every attempt of a message to a station carries the id of the latest message that station sent you with such a number, until the station acks or rejects a message of yours.
- A message that comes as `{MM}AA` is acked with a copy of its number, such as `:ack05}01`, and its `AA` settles your message with that id to that station as an ack does.
- An ack of the form `ackMM}AA` acks your message `MM`.
- A message from a station that sent it as `{MM`, without the closing brace, is owed nothing.
- The `AA` is not part of the text that is kept, so a repeat with another `AA` is a repeat.

## The Messages tab

The tab is laid out by its own width, not the window's, because the panel beside the map can be narrow on a wide screen.

- **600 px or more:** two columns, the list of conversations at the left and the open conversation at the right, a vertical line between them. With no conversation open the right side says "Choose a conversation, or a station's Message button".
- **Under 600 px** (a phone, a narrow panel): one of them fills the tab at a time. The list shows until you pick a conversation. Then the conversation shows with a back arrow `‹` at the left of its header; Esc does the same, and the focus returns to the row you came from.

Resize the panel and the layout follows, with the same conversation open.

### The list

- The conversations are listed with the newest message first. A row has the call (an overheard pair as "OH2AAA > OH2BBB"), the age, the last text on one line ("You: " before one of yours; "You asked for its status" for a query you sent), the number of messages that came in since you last looked, and a trash can at its right end.
- The open conversation is the filled row. A conversation with messages not seen that is not the open one has its text in bold and a bar at its left. A row is a button, so Tab walks the list.
- There is no New message button. A chat starts from a station: the **Message** button of its card on the map or in the Stations table opens the conversation, or creates it. In the Stations tab you can also type a call that was never heard into the filter, and **Message OH2XYZ** writes to it all the same.
- **Show overheard** (with an (i)) at the top of the list is off by default and remembered.
- A message counts as seen only while its conversation is open and visible: the Messages tab is the tab on show, the panel is not folded, the page is visible (a page in a background browser tab keeps counting), and on a narrow tab the conversation is shown and not the list. What was seen is kept in the browser.
- The count of messages not seen is a badge on the Messages tab, on the handle of the folded panel, in the header (a click opens the newest conversation with something new) and in the title of the browser tab (`(2) NeoAPRS`).

### The conversation

- The header has the call (and the back arrow on a narrow tab) and a small **Route** button at its right. It opens a box under the header with the path the messages to the station go by and the **RF only** tickbox; Esc or a click outside closes it. A dot on the button says that the route is not the default. An overheard pair has no Route.
- The thread is bubbles, yours at the right and theirs at the left, filling the height and scrolled to the newest. Under your message, small, are the time, the mark and state with the attempts ("attempt 3 of 4" while it is being sent), **Retry** or **Cancel** where they apply, and the chain of digipeaters its packet went by. A message that came in shows the route it came by in small type ("via OH2RCH-2").
- Each message of yours has a mark: a clock while it is being sent; a check once it is acked (the title has the time of the ack); a hollow check, a ring with a check in it, when it was sent and no ack is expected; a cross when it failed or was rejected; a dash when it was cancelled. A message that came in has its time only.
- The box to write in is at the bottom, always in view, in one line: the text, the bytes left of the 67 ("67 left") and **Send**. Send is off while the TNC is not connected, or the text is empty or too long. There is no To field: the conversation is the station.
- An overheard pair has no box to write in and no Route, only the bubbles, since the messages are not yours to answer.
- What you typed stays when you go back to the list or open another conversation.
- **Esc** deselects the open conversation, on a wide tab as on a narrow one. The Route box, if it is open, takes the first Esc. A text box with text in it keeps the text and the conversation; with it empty, Esc goes through.
- The **trash can** on a row deletes the whole conversation after two clicks ("sure?" for 5 seconds). On an overheard pair it deletes every overheard message of the pair. A single message has no delete button.

### The chain of a message

Under a message of yours the thread shows the digipeaters its latest attempt went by, as a chain: `you → OH2RCH-2 → OH2RDG → OH2CUB-7`. The line above it already says which attempt it is ("attempt 3 of 4"), so only the latest attempt's chain is shown.

- A copy of your message that the radio hears again (also one an iGate gated back) is linked to the attempt it belongs to, and each hop of the path that a copy was heard with is marked as used. A hop that is used implies the hops before it, so `OH2RCH-2,OH2RDG*` shows both.
- A hop heard is green with a check. A hop not heard is grey with a `?`; its title says "beyond what this station can hear" when that digipeater was never heard direct. A hop seen only in a copy gated back from the internet is blue with `internet`.
- The recipient at the end is green on the ack, red on failure and grey while the message waits.
- Acks and copies of other messages are not linked. The chain goes with the message when it or its conversation is deleted, and a retry starts a new chain.

### One text to several stations

Press Ctrl+click (Cmd+click on a Mac) on several stations, then **Message these 3** on the map. The Messages tab opens a **group compose** in place of a conversation. A call that is not a call, `EMAIL-2` or a repeat is left out.

Its header has the recipients as chips, each taken out by a click (the last one out closes the compose), and a close button. At the bottom are the text, "67 left" and **Send to 3**. Esc closes it, except while its text box has text in it.

Send makes one ordinary message to each recipient, each with its own id, ack, attempts and conversation, exactly as if sent one by one. They leave one after the other at the pace above. The compose then closes and nothing is opened. What you typed in it is kept apart from the drafts of the conversations.

## How the path of a message is chosen

You do not have to choose. Each attempt of a message to a station picks its path when it is sent:

1. If you gave the station a path of its own (below), every attempt goes by it.
2. Otherwise, if there is a **good heard path** to the station, attempts 1 and 2 go by it and attempts 3 and 4 by the beacon's path.
3. Otherwise every attempt goes by the beacon's path (the recommended path of your station's symbol, `WIDE1-1,WIDE2-1` for a moving station and `WIDE2-1` for a fixed one, unless you changed it).

A heard path is **good** when it is recent and repeated, in plain words:

- The station was heard **direct** (no digipeater repeated its packet) at least twice in the last 60 minutes: the path is then no digipeaters at all.
- Otherwise, take the latest route by which at least two of its packets came within the last 60 minutes, and send by it turned round (heard "via OH2RCH-1 → OH2RCH-3", send by `OH2RCH-3,OH2RCH-1`). A route with a hop that has no call (`WIDE1*`), a packet that came through an iGate from the internet, or more than 3 digipeaters is never used.

One packet is luck, an hour-old route may be gone, so the choice is made again at every attempt: a route learned while the message is being sent counts for the next attempt, one that has gone stale does not. The message to the email gateway `EMAIL-2`, bulletins and groups, and the answers to queries always go by the beacon's path. The path of each attempt is in the delivery chain of the message (the chips of its details). An ack goes by the station's own path, else the beacon's.

The numbers (60 minutes, 2 packets, 3 digipeaters, 2 attempts) are fixed in the program; they are not settings.

## A path for each station

A station can have a path of its own, which overrides the automatic choice: the digipeaters that everything you send to it goes by, which means its messages (every attempt), their repeats and the acks of the messages it sends you. It is up to 8 digipeater calls separated by commas, checked as the beacon's path is, or the word `DIRECT` for no digipeaters at all. An empty field is not a path: it is the automatic choice.

The path belongs to the call as written, so OH2RDG and OH2RDG-7 have one each. A change counts from the next frame, and a message that is being sent goes on by the new path. The paths are yours, kept in the database apart from the station cache, so they survive a rebuilt cache and a restart.

Set it in the field under **Route** of a conversation. It is saved when you change the field and leave it (Enter does it). The x beside the field, or emptying it, gives the choice back to the automatic one.

One line under the field says what the messages go by:

- **Automatic: via OH2RDG,OH2RCH-2, then WIDE2-1**: the heard path for attempts 1 and 2, then the beacon's.
- **Automatic: direct, then WIDE2-1**: the station is heard direct.
- **Automatic: WIDE2-1**: nothing good was heard.

(`WIDE2-1` is the recommended path of a fixed station, as in these examples; a moving station's is `WIDE1-1,WIDE2-1`.)
- **Your path: ...** when you set one.

The line is worked out when the station's row is sent, so it follows the station's next packet.

### RF only

The APRS-IS rules say that an iGate does not put on the internet a packet whose path holds `NOGATE` or `RFONLY`. An iGate may honour that; it is not required to.

A station marked **RF only** (the tickbox beside the path, in the header of a conversation; its title says "iGates do not put these messages on the internet") gets `RFONLY` as the last element of the path of every frame you send to it: each attempt of a message, each ack of one of its messages and each answer to one of its queries. A path that holds `RFONLY` or `NOGATE` already gets no second one.

A path of 8 digipeaters has no room for it. A message to the station is then refused with `path too long for RF only`. An attempt that is due waits (it is not used up; the log says why once). An ack or an answer is not sent. The email gateway `EMAIL-2` is on the internet and can never be RF only.

## How a packet reached us

The path of a received packet lists up to 8 digipeaters, and each has a has-been-repeated bit, written as a star (`OH2RCH-2*`). A digipeater that repeats a packet usually puts its own call in place of the alias it used (`WIDE1-1` becomes `OH2RCH-2*`). So the starred addresses, in order, are the **route**, and the last of them is the station whose transmission you heard.

- A starred alias (`WIDE1*`, `WIDE2-1*`, `TRACE2-1*`, and `WIDE`, `TRACE`, `RELAY`, `ECHO`, `GATE`, `TEMP`, `TRACK`, `SAR` with a digit and an SSID) is a hop whose call is not known: an anonymous one, written `?`.
- An address without a star has not been used and is not part of the route. A packet with no starred address came straight from its sender.
- Examples: `OH2RCH-2*` is "via OH2RCH-2"; `OH2RCH-3*,TRACE2-1` is also "via OH2RCH-3"; `WIDE1*,OH2RCH-2*,WIDE2-2` is "via ? → OH2RCH-2"; `OH2RCH-1*,OH2RCH-3*` is "via OH2RCH-1 → OH2RCH-3".

The route is worked out when the packet is heard. It is shown in the Packets tab and with every message that came in or was overheard. Of two copies of a message that arrive by different routes, the first heard is kept; both copies stay in the packet log with their own paths.

For each station NeoAPRS counts how many of its packets came direct and how many by each route, from the packets heard since the start and the latest 2000 that the database kept. It keeps the 8 most frequent routes of a station. When a ninth comes, the one with the fewest packets goes, the one heard longest ago first.

- The **best route** is the one most packets came by, direct included. With equal counts the one with fewer hops wins, then the one heard last.
- The **suggested path** (the Stations card says "send by ...") is that route turned round, because the station that repeated the packet last, nearest to you, is the first digipeater of a packet you send back. Direct suggests an empty path. "via OH2RCH-2" suggests `OH2RCH-2`. "via OH2RCH-1 → OH2RCH-3" suggests `OH2RCH-3,OH2RCH-1`.
- When the best route has an anonymous hop there is no call to name, and the suggestion is the general `WIDE1-1,WIDE2-1`; the card says "unknown repeater".
- No route is known for an object or an item, for your own station and for a station none of whose packets are left.

**Heard direct.** NeoAPRS also keeps when each station last came direct: the time of its latest packet with no repeated address in its path (not a third-party packet). A station heard direct in the last hour has a green ring on the map. A station heard direct has a green check mark after its call in the Stations table and on its card. The share of a station's packets that came direct is counted over the packets counted for the station (direct, by a digipeater, from the internet).

### Packets from the internet

An iGate that hears a station on the internet (the ack of a message you sent, a reply) puts it on the air wrapped in a frame of its own with its own call as the source. The information field starts with `}` and holds a whole packet in the text form. NeoAPRS opens the wrapper, one level only.

From then on the sender is the station inside the wrapper:

- an ack or a reject from it settles your message;
- a message from it is received and acked to it;
- a position or an object report updates its station and not the iGate's;
- a packet with your own call inside is ignored, as an echo is;
- a message heard both direct and from a gate is one message.

The route of such a packet starts at the gate: "via OH7JHF-1 (internet)", or "via OH7JHF-1 (internet) → OH2RCH-3" when the gate's frame was repeated. It counts as "from the internet" and **never for the suggested path**: the gate is not a digipeater of the way back, because the sender is on the internet and nothing says it can be reached by RF through that gate.

## What is kept

Every message is stored while the daemon runs: each message to you, each message you send with every change of its state and attempts, and the ack or reject you receive.

A message to another station that you only hear is kept too, as *overheard*. A message to a bulletin, announcement, group, `ALL`, `CQ`, `QST` or the weather service belongs to the board, not here. A query and a telemetry definition are in the packet log only. An overheard message is kept once for a repeat or a digipeater's copy within 30 minutes, and never acked. The acks and rejects of other stations are not messages.

Overheard messages are no conversation. The page lists them only when **Show overheard** is on, a pair of stations at a time.

Nothing is dropped. Every message, overheard ones included, is held and shown, and the daily clean-up leaves messages alone. A message goes only when you delete it. The one bound is a database with more than 10000 messages: a start then takes the latest 10000 and says so in the log as a warning, and the older ones stay in the database.

**Deleting.** The x of a conversation row removes every message of the conversation: the messages you sent to the station and the ones it sent you, from the database and from every page. Messages still being sent are cancelled first. Messages you only overheard stay, and so do the station's path and timeout. The call is read as a call (`oh2rdg` is `OH2RDG`), and SSIDs are different stations. For an overheard pair the x removes every overheard message from the first call to the second; your conversations are not touched.

A message that is deleted and heard again within 30 minutes is not kept again.
