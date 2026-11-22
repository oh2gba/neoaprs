# Bulletins: the message board

A bulletin is a message to everyone, shown on every station's board. Use it for net times, events, warnings. The (i) at the top of the tab says so with a picture.

The Bulletins tab shows the message board and has a group box at its bottom, **Post a bulletin**, to post to it.

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

The tab shows the board newest first in four sections: announcements, bulletins, group messages (the group bulletins and the messages to `ALL`, `CQ` and `QST`), weather service. It is read from the top; a stream oldest first would open on the weather service. Every entry has its sender, what it is addressed to (the group of a group bulletin, else the slot), the text, how often it was heard and how long ago it was last heard.

Nothing leaves the board on its own: no ageing, no limit, no daily clean-up. An entry stays until you delete it with the trash can on its row (two presses, the second after "sure?"). The same bulletin heard again afterwards is a new entry, heard once.

A badge on the tab counts the entries whose text was first heard since the tab was last on show. The tab is on show when it is the tab in front, the panel is not folded and the page is visible. What was seen is kept in the browser.

## Posting

The box has a row for each field, and each row has its (i) after it that says what the field is for; the Kind's and the Group's have a small picture. The **Kind** is one of three:

| Kind | who shows it | how it is sent | Sent for | what it is for |
|---|---|---|---|---|
| **Bulletin** | every station that hears it | at once, twice more in the first minutes, then every 20 minutes | 1, 2, 4, 8 or 12 hours (4 until you choose) | what matters now: a road closed, a net tonight |
| **Announcement** | every station that hears it | at once, twice more in the first minutes, then every hour | 1, 3 or 7 days (3 until you choose) | what stays true for days: a meeting next week, a digipeater off the air |
| **Group bulletin** | every station that hears it, unless its operator has picked other groups to show and not this one; NeoAPRS shows every group's | as a bulletin | as a bulletin | news for one group: a club, a weather net |

How a group bulletin works: the group's name is part of the address (`BLN3HAMS`), so every station that hears the packet receives it, and every station shows it unless its operator picked other groups to show and not `HAMS`. NeoAPRS shows the group bulletins of every group it hears, under Group messages.

Nobody acknowledges any of them, which is why they are sent more than once. To reach particular stations, with an acknowledgement from each, send them a message instead (Messages tab, Stations).

Under the kind:

- **Sent for**, how long the post is sent, counted from its first packet. It starts at what you chose for the last post of that kind;
- the **Group**, a name of one to five letters and digits, for a group bulletin. The row is greyed for the other kinds;
- the **Text**, with the characters of the 67 it has left;
- **Send on**, only while several radios that can send are on: the beacon's row of ticks, a tick for each of them by its name, the radios this post goes out on. A new post is ticked as the one you posted last; the last tick ticked is greyed. The ticks go with **Post**. With one radio that can send the row is not there;
- **Post**, which is on when the post can be sent.

A new post takes the next free number or letter of its kind by itself: the lowest that holds no post of yours, an ended one included. A bulletin takes `BLN0` to `BLN9`, an announcement `BLNA` to `BLNZ`, a group bulletin `BLN0` to `BLN9` with its group, counted for each group apart. When all of them are taken, **Post** is off for that kind. A post is never replaced or changed: delete one on the board, and post anew.

What goes on the air:

- A **bulletin** is `BLN0` to `BLN9`.
- An **announcement** is `BLNA` to `BLNZ`.
- A **group bulletin** is `BLN`, a number and a group name of one to five letters and digits (`BLN3HAMS`).
- The text is at most 67 characters of printable ASCII without `|`, `~` and `{`.
- The messages to `ALL`, `CQ` and `QST` and the weather service's are not posted from here.

### The packet

A bulletin is a message without an id (chapter 14 of the specification), sent on its radios, each by that radio's path (`radio/<id>/path`): `:BLN3     :Snow expected in Tampa RSN`, an announcement `:BLNQ     :Mt St Helen digi will be QRT this weekend`, a group bulletin `:BLN4WX   :Stand by your snowplows`. The addressee is padded to nine characters.

Nobody acknowledges a bulletin, so it is sent more than once:

- **a bulletin** (and a group bulletin) at once, after 2 minutes, after 6, and then every 20 minutes until its Sent for after the first: 5 packets for 1 hour, 8 for 2, 14 for 4, 26 for 8, 38 for 12;
- **an announcement** at once, after 2 minutes, after 6, and then every hour until its Sent for after the first: 26 packets for 1 day, 74 for 3, 170 for 7.

The times are the same on every radio and by every path: the digipeaters of the path do not change them.

Nothing is sent after its Sent for is over, also when it ended while NeoAPRS was not running. You can have at most 36 posted at once.

A bulletin goes on the radios ticked when it was posted, and so do its repeats, once on each in every round ([radio.md](radio.md#what-goes-on-which-radio)); with one radio that can send, on that one. While a radio it goes on is Mercury or LoRa, its repeats come every 30 minutes on each of its radios, not every 20. **Post** is off while no radio ticked is connected, with that as its title ("The radio is not connected", or "FM: not connected" while several radios are on), and while no tick is ticked (the radios of the last post were switched off).

Nothing is posted while the call is not set. What is due waits for the radio, and one packet goes out when it is back. At most one packet of yours of this kind (an object or a bulletin) goes out every 10 seconds, and a restart sends no burst ([objects.md](objects.md#when-it-is-sent)).

### Yours on the board

Your posts are on the board in their section, under your call and marked "ours". Each shows how often it was sent and when it goes out next, and "ended" once its schedule is over; it stays until you delete it. While several radios that can send are on, each has the tags of the radios it goes out on after "ours", as My objects has them: two by name, then "+n", whose hover names the rest.

The trash can on a post of yours asks twice, stops it, and takes it off the board and out of the database. Its hover title says "Delete (stop sending)". The one on an entry that was heard is the board's delete.

A bulletin of yours that a digipeater repeats comes back as a packet from your own call. NeoAPRS takes it for a copy of what you sent, not a bulletin from another station, so the board of what was heard never holds yours.
