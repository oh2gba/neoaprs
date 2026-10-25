# Objects and items of your own

The Objects tab makes an object, shows it on the map as yours, changes it and kills it. NeoAPRS sends it on the air by a schedule of its own. The list of your objects is above and the form is always under it: with no object selected the form adds a new one, with one selected it changes that one.

- An **object** (chapter 11 of the specification) has a name of 1 to 9 characters and a time stamp.
- An **item** has a name of 3 to 9 characters and no time stamp. The tab no longer makes new ones (objects are recommended on RF; the specification advises against the item format on the air), but an item you made before is still listed, can be changed and killed, and is sent as before.

Objects of other stations that you hear are stations of their own on the map, named by the object and marked with who reported them. A copy of one of yours that comes back is none of them ([below](#heard-back-and-taken-over)).

## Making one

The form is at the bottom of the tab, under the list of your objects (oldest first, scrolled to the newest, so that it is next to the form), and it is there all the time. It is the box that every tab writes in; its fields scroll on a short screen, and on a phone the list keeps its own share of the screen and scrolls. With no row selected it makes a new object at the place you are. The line under the fields has, at the right, "N left" for the comment, a plain **Cancel** and the main button, **Add**.

**Esc** and **Cancel** give up what is in the form: they leave the selected row, if there is one, and clear the form without saving. A field that still has text keeps its first Esc, and while the map waits for a click Esc ends that first. **Cancel** is there for a screen without a keyboard.

- **Name.** Printable ASCII, case-sensitive, none of `!`, `_`, `|` and `~`, no blank at either end. It is never your own call, and never the call of a station that was heard.
- **Symbol.** The picture and its name, as in the Beacon tab: a click on it opens the picker.
- **Location.** As in the Beacon tab and the setup guide ([beacon.md](beacon.md#the-location)): a plain **Choose on map** button and a click on the map (Cancel while the map waits), the place as text beside the button, and the latitude, longitude and locator behind a click on the place, open while the place is missing or wrong. The map shows a pin where it is while the tab is in front.
- **Comment.** 43 characters, 36 behind a course and speed.
- **Moving.** A closed heading with the **course** in degrees and the **speed** in km/h: each, both or neither. It is open when the object you change already has a course or a speed; empty, the object does not move.
- **Path.** The placeholder is the beacon's path, which an empty field means. Up to 8 digipeaters, or the word `DIRECT` for none at all. `RFONLY` or `NOGATE` in it keeps the iGates from putting it on the internet.
- **QRU group.** Empty for none. 1 to 8 letters and digits, written in capitals (`FOOD`, `RP70`), and not `INFO` or `NEXT`. A station that asks for the group is sent the object ([below](#objects-sent-only-when-asked)).
- **Send only when asked.** Off: the object is sent on the schedule as always. On: it is kept and shown, and sent only to a station that asks for it.

A field with something wrong is red and says what. The main button waits until nothing is wrong. Adding a name that is there changes that object. You can have at most 50 objects and items at once, and nothing is made while the call is not set.

**On the map** an object of yours has a dashed ring and a marker that you can drag. Where you drop it is its new place (the same as a change in the form, with everything else as it was). It never times out. Its card has **Edit** (the Objects tab opens with the object selected) and **Kill**, in place of Message and Forget, and none of a station's fields.

**Changing one.** Click its row, as you would a row of the Nearby tab: the row is highlighted, the object is selected on the map (its card opens and the map goes to it; on a phone the tab stays, the map has it when you go there), and the form under the list has it. The name stays, as it is the object's identity; the main button now reads **Save**. When the daemon has the changed object the selection is let go of and the form is clear for the next one. **Esc** and **Cancel** leave the selection. An object whose kill is going out cannot be selected.

**In the Objects tab** each object has an x that asks twice (the second press after "sure?") and kills it. A row says how often the object was sent and when it goes out next ("sent 3 times, next in 12 min"), "waiting" when that time has passed because the radio is away, "killing" for an object whose kill is going out, and "sent only when asked" for one that is never sent on the schedule. An object with a QRU group shows the group after its kind.

## The packet

A packet from your call to `APZNEO`, by the object's path, else the beacon's. The information field is the object's `;`, its name padded with blanks to nine characters, `*` for a live object, the time stamp, the position, the course and speed when it has them, and the comment.

- The time stamp is the day, hour and minute of the moment of sending, in UTC with a `z`. Each copy carries its own.
- The position is the uncompressed form rounded to the hundredth of a minute.
- The course is `CSE/SPD`: three digits of degrees (360 is north, 000 is none) and three of knots.

These are the specification's own examples. An object at 2345 hours zulu on the 9th, heading 88 degrees at 36 knots:

```
OH2GBA>APZNEO,WIDE1-1,WIDE2-1:;LEADER   *092345z4903.50N/07201.75W>088/036
```

An item (`)`, the name, `!`, no time stamp; the Hurricane Brenda symbol `\@`):

```
OH2GBA>APZNEO,WIDE1-1,WIDE2-1:)BRENDA!4903.50N\07201.75W@088/036
```

A killed object or item is the same packet with `_` where the `*` or the `!` was: `;LEADER   _092345z4903.50N/07201.75W>088/036`. The specification's table of data types lists a `-` in front of the name for a killed object, which no program on the air reads. Every APRS program kills with the `_`, and so does NeoAPRS.

## When it is sent

The schedule is the decay algorithm of the specification's "Packet Timing" (chapter 2): transmit a new packet once and n seconds later, double n each time, and when n reaches the net cycle time continue at that rate. A new or changed object goes out at once, then after 1, 2, 4, 8 minutes and so on, never more than the net cycle time of its path apart, until it is changed (the decay starts again) or killed.

The net cycle time follows the number of digipeaters of the path (chapter 2, point 4):

| digipeaters | net cycle time |
|---|---|
| none or one | 10 minutes |
| two (`WIDE1-1,WIDE2-1` is two: the recommended path of a moving station) | 20 minutes |
| three or more | 30 minutes |

A `WIDEn-N` counts the N hops it has left. `RFONLY`, `NOGATE` and the markers of the internet count none.

So with `WIDE1-1,WIDE2-1` the packets go out at minute 0, 1, 3, 7, 15, 31 and then every 20 minutes (51, 71 ...). With `WIDE2-1`, the recommended path of a fixed station, they go at 0, 1, 3, 7, 15, 25 and then every 10. With `WIDE3-3` they go at 0, 1, 3, 7, 15, 31, 61 and then every 30.

- No packet of one object goes out less than a minute after the one before it, a change included. A change asked for sooner waits.
- At most one packet of yours of this kind (an object or a bulletin) goes out every 10 seconds, whatever is due. A restart with many objects, or a radio that comes back, sends no burst.
- A **kill** is sent three times (at once, a minute later and three minutes after the kill). Then the object is forgotten: removed from the database and from the list. It leaves the map as soon as it is killed. An object that was never sent is removed at once and nothing is said of it.

## The call and the radio

Nothing is made or sent while the call is not set (the log says `no object sent: set your call first`, once). Nothing is sent while the radio is not usable: the TNC is not connected, silent, not yet confirmed, or settling after KISS ON.

What is due then is not skipped and not made up. The log says once for the outage `the object is due and the radio is silent: it goes out when the radio is back`. The first moment the radio is usable one packet goes out for each object that was due, however many intervals went by, and the schedule goes on from there.

A frame that cannot be made, such as a beacon path of more than 8 digipeaters, is told once. The objects that have a path of their own are not held up by it.

The first transmission is not tried by NeoAPRS's tests: make an object, then look for it on aprs.fi or on another station's screen, before you leave objects on the air.

## Objects sent only when asked

Some objects are not worth a place on the air all the time: the pubs, the petrol stations, the repeaters round the town. Give them a **QRU group** and tick **Send only when asked**, and NeoAPRS keeps them and sends them to a station that asks. This is the QRU server of APRSISCE/32 and YAAC. QRU is the Morse abbreviation for "have you anything for me?".

An object that has a group but is not ticked is sent on the schedule as well, and is also given to a station that asks. An object that is ticked is never sent on the schedule: nothing goes out when you make or change it, and killing it removes it at once.

A station asks by sending a **message to the addressee `QRU`** (not to your call). Every QRU server in range answers.

| the message | the answer |
|---|---|
| `INFO` (or `?`) | a message to the asker with the groups you have near it and how many objects each has: `de OH2GBA-10:FOOD(3) FUEL(1) Max 5@50km`. The last part is the most objects it will send and the distance. A long list is two messages, the first ending in `+`; what does not fit is left out |
| `FOOD` | the objects of the group, the nearest first, at most 5, as object packets 10 seconds apart, and then a message `Sent 3 FOOD Objects Max 5@50km de OH2GBA-10`. When more are near: `Sent 5 of 12 FOOD Objects, NEXT for more. de OH2GBA-10` |
| `NEXT` | the following objects of the group that station asked for last (for an hour) |
| `INFO 250`, `FOOD 250` | the same within 250 km instead of 50 km |

"Near" is the distance from the asker's last position that you heard to the object. A station whose position you do not know is offered every object, since it asked you and so can hear you. A server with nothing near the asker does not answer.

- The answers go by the path of the station that asked, are not retried and have no message id. A request that carries an id is acked, as a query to you is. Nothing is sent while the TNC is not connected or the call is not set.
- The same request from the same station within 30 seconds is answered once.
- A message to `QRU` is not kept in Messages. While you have no object with a group it is a message to another station like any, and is kept as one you overheard.
- `?APRSO` also gives these objects.
- You can have 50 objects and items at once, these among them.

## Heard back, and taken over

A packet from your own call that comes back (a digipeater's copy of your object, an iGate's, the TNC's echo) is no report of an object. It counts as proof that you are heard (it moves the time you were last heard) and nothing else. So there is never a second object of the same name.

The specification's "Replacement" is kept: any station may take over reporting an object by sending it, and the original station ceases to transmit it. When another station reports a live object with the name of one of yours, yours is dropped without a kill (the log says who took it over) and the map shows theirs. Another station's kill of the name does not end yours.

## Kept

Your objects are kept in the database after every change and every packet. A restart goes on where the schedule stopped: the objects are on the map at once, nothing is sent for the restart, a kill that was not sent yet is sent, and the next packet is due when the schedule says. They are not in the station cache.
