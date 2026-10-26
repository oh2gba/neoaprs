# Bulletins: the message board

A bulletin is a message to everyone, shown on every station's board. Use it for net times, events, warnings. The (i) at the top of the tab says so with a picture.

The Bulletins tab shows the message board and has a box at its bottom to post to it.

## The board

A message addressed to one of these is no conversation. It is never acked, whatever id it carries, it is not in the Messages tab, and it is not kept as a message, not even an overheard one.

| addressee | what it is |
|---|---|
| `BLN0` to `BLN9` | a bulletin |
| `BLNA` to `BLNZ` | an announcement |
| `BLN`, a number or letter, then a group name of up to five characters (`BLN3HAMS`) | a group bulletin, for the group `HAMS` |
| `ALL`, `CQ`, `QST` | a group message |
| `NWS-xxxxx`, `SKY`, `CWA` (the last two with up to three more characters) | the weather service |

The board holds one entry for each **sender and slot**. The slot is the addressee as written, in capitals: `BLN1`, `BLNA`, `BLN3HAMS`, `QST`. A message that an iGate put on the air is from the sender inside it.

- A sender sending the slot again replaces the text. The entry starts again with one hearing, and "first heard" is when the new text was heard.
- The same text again moves "last heard" and counts one more hearing. The copies of one transmission that come by different digipeaters within 10 seconds are one hearing.
- A message with no text adds nothing.
- A restart finds the board as it was.

The tab shows the board newest first in three sections: announcements, bulletins, group messages. It is read from the top; a stream oldest first would open on the weather service. Every entry has its sender, what it is addressed to (the group of a group bulletin, else the slot), the text, how often it was heard and how long ago it was last heard.

Nothing leaves the board on its own: no ageing, no limit, no daily clean-up. An entry stays until you delete it with the trash can on its row (two presses, the second after "sure?"). The same bulletin heard again afterwards is a new entry, heard once.

A badge on the tab counts the entries whose text was first heard since the tab was last on show. The tab is on show when it is the tab in front, the panel is not folded and the page is visible. What was seen is kept in the browser.

## Posting

The box at the bottom has:

- the **kind**: a bulletin, an announcement or a bulletin to a group;
- the **identifier**;
- the **group name**, for a bulletin to a group;
- the **text**, with the characters of the 67 it has left;
- **Post**, which is on when the post can be sent.

A small (i) beside the kind says what they are. A bulletin is for everyone and nobody acknowledges it. A bulletin to a group is for the stations that follow that group name. To reach particular stations, with an acknowledgement from each, send them a message instead (Messages tab, Stations).

- A **bulletin** is `BLN0` to `BLN9`.
- An **announcement** is `BLNA` to `BLNZ`.
- A **bulletin to a group** is `BLN`, a number and a group name of one to five letters and digits (`BLN3HAMS`).
- The text is at most 67 characters of printable ASCII without `|`, `~` and `{`.
- The messages to `ALL`, `CQ` and `QST` and the weather service's are not posted from here.

### The packet

A bulletin is a message without an id (chapter 14 of the specification), sent by `beacon/path`: `:BLN3     :Snow expected in Tampa RSN`, an announcement `:BLNQ     :Mt St Helen digi will be QRT this weekend`, a group bulletin `:BLN4WX   :Stand by your snowplows`. The addressee is padded to nine characters.

Nobody acknowledges a bulletin, so it is sent more than once:

- **a bulletin** (and a group bulletin) at once, after 2 minutes, after 6, and then every 20 minutes until 4 hours after the first: 14 packets;
- **an announcement** at once, after 2 minutes, after 6, and then every hour until 72 hours after the first: 74 packets.

A text posted to a slot that holds one replaces it and starts the schedule again, never within a minute of the last packet of the slot. The same text posted again, once the schedule is over, goes out again. You can have at most 36 posted at once.

Nothing is posted while the call is not set. What is due waits for the radio, and one packet goes out when it is back. At most one packet of yours of this kind (an object or a bulletin) goes out every 10 seconds, and a restart sends no burst ([objects.md](objects.md#when-it-is-sent)).

### Yours on the board

Your posts are on the board in their section, under your call and marked "ours". Each shows how often it was sent and when it goes out next, and "ended" once its schedule is over; it stays until you delete it or post it again.

The trash can on a post of yours asks twice, stops it, and takes it off the board and out of the database. Its hover title says "Delete (stop sending)". The one on an entry that was heard is the board's delete.

A bulletin of yours that a digipeater repeats comes back as a packet from your own call. NeoAPRS takes it for a copy of what you sent, not a bulletin from another station, so the board of what was heard never holds yours.
