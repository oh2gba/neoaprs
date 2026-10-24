# Objects and items of your own

The Objects tab makes an object or an item, shows it on the map as yours, changes it and kills it. NeoAPRS sends it on the air by a schedule of its own.

- An **object** (chapter 11 of the specification) has a name of 1 to 9 characters and a time stamp.
- An **item** has a name of 3 to 9 characters and no time stamp.

Objects of other stations that you hear are stations of their own on the map, named by the object and marked with who reported them. A copy of one of yours that comes back is none of them ([below](#heard-back-and-taken-over)).

## Making one

**New** opens the form at the bottom of the tab, under the list of your objects (oldest first, scrolled to the newest, so that it is next to the form). It is the box that every tab writes in; its fields scroll on a short screen. The line under them has, at the right, "N left" for the comment, **Cancel** and **Save**. **Esc** closes the form without saving, as Cancel does (a field that still has text keeps its first Esc; while the map waits for a click, Esc ends that first).

- **Name.** Printable ASCII, case-sensitive, none of `!`, `_`, `|` and `~`, no blank at either end. It is never your own call, and never the call of a station that was heard.
- **Object or item.** A new one is an object unless you choose item: objects are recommended on RF (the specification advises against the item format on the air).
- **Symbol.** A picture and its name, as in the Beacon tab: Change opens the picker.
- **Location.** As in the Beacon tab: a **Choose on map** button and a click on the map (Cancel while the map waits), the place as one line under it, and the latitude and longitude behind **Enter coordinates**, which is open while the place is missing or wrong. The form shows a pin where it is.
- **Comment.** 43 characters, 36 behind a course and speed.
- **Moving.** A closed heading with the **course** in degrees and the **speed** in km/h: each, both or neither. It is open when the object you change already has a course or a speed; empty, the object does not move.
- **Path.** The placeholder is the beacon's path, which an empty field means. Up to 8 digipeaters, or the word `DIRECT` for none at all. `RFONLY` or `NOGATE` in it keeps the iGates from putting it on the internet.

A field with something wrong is red and its title says what. Save waits until nothing is wrong. Saving a name that is there changes that object. You can have at most 50 objects and items at once, and nothing is made while the call is not set.

**On the map** an object of yours has a dashed ring and a marker that you can drag. Where you drop it is its new place (the same as a change in the form, with everything else as it was). It never times out. Its card has **Edit** (the Objects tab opens with it) and **Kill**, in place of Message and Forget, and none of a station's fields.

**In the Objects tab** each object has **Edit** and an x that asks twice (the second press after "sure?") and kills it. A row says how often the object was sent and when it goes out next ("sent 3 times, next in 12 min"), "waiting" when that time has passed because the radio is away, and "killing" for an object whose kill is going out.

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

## Heard back, and taken over

A packet from your own call that comes back (a digipeater's copy of your object, an iGate's, the TNC's echo) is no report of an object. It counts as proof that you are heard (it moves the time you were last heard) and nothing else. So there is never a second object of the same name.

The specification's "Replacement" is kept: any station may take over reporting an object by sending it, and the original station ceases to transmit it. When another station reports a live object with the name of one of yours, yours is dropped without a kill (the log says who took it over) and the map shows theirs. Another station's kill of the name does not end yours.

## Kept

Your objects are kept in the database after every change and every packet. A restart goes on where the schedule stopped: the objects are on the map at once, nothing is sent for the restart, a kill that was not sent yet is sent, and the next packet is due when the schedule says. They are not in the station cache.
