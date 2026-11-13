# Skeds: when stations will be on the air

On HF there are few stations, so two of them have to agree on a time and a frequency to hear each other. A sked says when you will be on the air and on which dial, so that another station can come and meet you there. The (i) at the top of the tab says that the board is public and not sent by radio.

The Skeds tab, after Bulletins, shows the board of skeds to come and has a group box at its bottom, **Post a sked**. It needs no radio, and it is on every station.

The board is a public list on the project's page, neo.oh2gba.eu. Nothing here goes over the air.

## The board

A sked is a call, a start and an end, a dial and a short note. The tab lists the skeds to come, the nearest first. A row has:

- the time in UTC, such as "Sat 14 Nov 18:00 to 20:00 UTC", and how long until it starts ("in 3 h", "now" while it runs). Your own time is in the hover text;
- the dial, such as `7.0541 MHz USB`;
- the calls that will be there. Skeds with the same times and the same dial are one row that lists their calls;
- the note, on one line. The whole note is in the hover text.

A row with a sked of yours has a trash can, which asks twice ("sure?") and then takes the sked off the board for everybody. Any other row has **Join**, which posts a sked of yours with the same times and the same dial, so that the stranger sees that someone will come. The column of these two buttons is as wide in every row, so nothing moves. **Join** is off while posting is not possible.

A sked is on the board until it ends. There is no change: to change a sked, delete it and post it again.

A badge on the tab counts the skeds of other stations that you have not seen. The tab is on show when it is the tab in front, the panel is not folded and the page is visible. What was seen is kept in the browser.

NeoAPRS reads the board a minute after it starts and every six hours while it runs. The tab asks for it again when it comes on show and every 15 minutes while it stays on show, though the program reads it at most every 15 minutes whatever the page asks. The last board is kept, so the tab has something to show after a restart, and while the board cannot be reached it shows the skeds read last.

## Posting

The box has a row for each field:

- the **day**, one of the next 30 UTC days, written in the language of the page;
- the **time**, from and to, in half hours. The label says UTC. A "to" that is not after the "from" is the next day, so a sked is never longer than 24 hours;
- the **frequency**: one of the dials the project suggests, or **Other**, which brings a row to type one in the form `7.0541 MHz USB` (or `LSB`);
- the **note**, one line of at most 80 characters, with the characters it has left.

The button reads **Post on neo.oh2gba.eu**. It is on when there is a call, the board can be reached and the form is right. A sked that has ended already marks its "to" and cannot be posted. RX only does not matter: nothing here is sent by radio.

The box opens on today, from the next half hour for an hour, on the first dial the project suggests. The note is cleared when the board has your sked; a post that was refused stays for you to correct.

## What goes over the internet

Reading the board sends nothing about your station. Posting sends your call, the two times, the dial and the note, only when you press **Post**, and a random secret code that your installation made once. The board keeps only a scrambled form of that code with the sked, so only the installation that posted a sked can delete it. The code is in the data folder, which an uninstall leaves, so it survives a reinstall.

A sked under your call that another installation posted can be removed only by the project. On a new computer, the skeds that the old one posted cannot be deleted from it, and end by themselves.

## Limits

- A sked may start up to 30 days ahead and is at most 24 hours long.
- At most five skeds to come for one installation, ten under one call, and 100 on the board.
- At most ten posts an hour from one address. The address is scrambled for the hour and forgotten, as the project page says.

A post that is refused says why, in a short note that goes away by itself: too many posted lately, no room on the board, the sked has ended, or the board could not be reached just now. When the board cannot be reached, Post is off and the tab says nothing; it works again when the board is back.

The project can close the board. The tab then shows the skeds without the box.

## On the project page

The project page shows the same skeds under the HF band when there are any to come: the call, the time in UTC and the dial of each, never the note. The section is not there while the board is empty.

Not in this version: a sked that repeats ("every Saturday": enter the weeks to come one by one), a reminder before a sked, and skeds on the map.
