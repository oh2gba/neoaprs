# HF tests: meeting another station on HF

The HF tests tab is for stations trying APRS on HF: you say when you will be on the air and on which frequency, so that another station can test with you. On HF there are few stations, and two of them have to agree on a time and a frequency before they can hear each other at all.

The tab comes after Bulletins, and is always there, with or without a Mercury radio ([radio.md](radio.md#the-mercury-modem)): you may want to see when others are on before your radio is set up, or announce a test of your own. It shows the tests planned by other stations and by you, and has a button at its bottom, **Plan a test**. Reading and posting need no radio: the board is on the web.

The tests are kept on a public board on the project's page, neo.oh2gba.eu. Nothing here goes over the air. The (i) at the top of the tab says so.

## The board

A test is a call, a start and an end, a dial and a short note. The tab lists the tests to come, the nearest first. A row has:

- the time in UTC, such as "Sat 14 Nov 18:00 to 20:00 UTC", and how long until it starts ("in 3 h", "now" while it runs). Your own time is in the hover text;
- the dial, such as `7.0541 MHz USB`;
- the calls that will be there. Tests with the same times and the same dial are one row that lists their calls;
- the note, on one line. The whole note is in the hover text.

A badge on the tab counts the tests of other stations that you have not seen. The tab is on show when it is the tab in front, the panel is not folded and the page is visible. What was seen is kept in the browser.

NeoAPRS reads the board a minute after it starts and every six hours while it runs. The tab asks for it again when it comes on show and every 15 minutes while it stays on show, though the program reads it at most every 15 minutes whatever the page asks. The last board is kept, so the tab has something to show after a restart, and while the board cannot be reached it shows the tests read last.

## Planning a test

**Plan a test** opens a window with a row for each field:

- the **day**, one of the next 30 UTC days, written in the language of the page;
- the **time**, from and to, in half hours. The label says UTC. A "to" that is not after the "from" is the next day, so a test is never longer than 24 hours;
- the **frequency**: one of the dials the project suggests, or **Other**, which brings a row to type the dial as a number alone, `28.140` or `28,14`: MHz and USB are fixed;
- the **note**, one line of at most 80 characters, with the characters it has left. Say there what you will try, such as your power or your antenna.

The button reads **Post on neo.oh2gba.eu**. It is on when there is a call, the board can be reached and the form is right. A test that has ended already marks its "to" and cannot be posted. RX only does not matter: nothing here is sent by radio.

The window first opens on today, from the next half hour for an hour, on the first dial the project suggests. When the board has your test, the window closes and the note is cleared; a post that was refused stays open for you to correct. **Cancel**, the cross or Esc close it without posting, and it opens again with what you had chosen.

## Joining a test

A row of another station has **Join**. It opens **Plan a test** with the same day, times and dial, so that the other station sees that someone will come once you post it. **Join** is off while posting is not possible.

## Deleting a test

A row with a test of yours has a trash can, which asks twice ("sure?") and then takes the test off the board for everybody. The column of Join and the trash can is as wide in every row, so nothing moves.

A test is on the board until it ends. There is no change: to change a test, delete it and plan it again. A test you delete while it runs ends then, and goes to the past tests.

## Past tests

Under the board, **Past tests** is folded: its arrow opens it, and your browser remembers whether it is open. It lists the tests that have ended, the newest first: the time, the dial, the calls that were there and the note, in the same rows as the board. A test leaves the board for this list when it ends, while the tab is open. A past test cannot be joined. The list shows the 20 newest, and each stays for 30 days after its end. The bin on a past test takes it off your own list, on every screen of your NeoAPRS; other stations still see it.

## What is public

The board is public: anyone can read it in the program or on the project's page. Reading it sends nothing about your station.

Posting sends your call, the two times, the dial and the note, only when you press **Post**, and a random secret code that your installation made once. The board keeps only a scrambled form of that code with the test, so only the installation that posted a test can delete it. The code is in the data folder, which an uninstall leaves, so it survives a reinstall.

A test under your call that another installation posted can be removed only by the project. On a new computer, the tests that the old one posted cannot be deleted from it, and end by themselves.

## Limits

- A test may start up to 30 days ahead and is at most 24 hours long.
- At most five tests to come for one installation, ten under one call, and 100 on the board.
- At most ten posts an hour from one address. The address is scrambled for the hour and forgotten, as the project page says.

A post that is refused says why, in a short note that goes away by itself: too many posted lately, no room on the board, the test has ended, or the board could not be reached just now. When the board cannot be reached, Post is off and the tab says nothing; it works again when the board is back.

The project can close the board. The tab then shows the tests without the box.

## Chat

Under the tests is the chat: one room for every station that uses the tab, to say "QRV on 7.0541, anyone?" or "heard you, 5 by 9" without leaving NeoAPRS. It goes over the Internet, through the project's server, and never on the air.

- The lines are listed oldest first, each with its time in your own time (the whole date in the hover text), the call and the text. The list shows its newest line; while you scroll back to read older ones it stays where you are when a line comes.
- Write in the line at the bottom and press Enter or **Send**. The call shown with your lines is the one of the My station tab, with its SSID. Without a call the line is off; reading works.
- The text is kept until the chat has your line. If it could not be said (too many lines from here in a minute, the chat closed, the server not reached), the short note at the bottom of the page says why and the text stays for you to send again. A line being written stays when you go to another tab.
- A line is one line of at most 200 characters. Other people's lines are shown as text, as they wrote them.
- The chat keeps the newest 100 lines, so a station that was off for a while still finds what was said.
- The project can close the chat: the tab then says "The chat is closed." and the line is off; what was said stays to read.

NeoAPRS asks for the chat every 15 seconds while it runs, whether a page is open or not, so you are told of a new line as you are told of a message: the tab's badge counts the lines of others you have not seen, and the page's and the computer's notification tell you, once for the lines that came together ([notifications.md](notifications.md)). Your own lines, and those that were there when you first started NeoAPRS, never notify. **HF tests chat** in the **Notifications** group of the Settings tab switches the notifications of the chat off; the badge stays.

What is sent: only a line you wrote, with your call and the installation's secret code (the one of your tests). Asking for the chat sends nothing about your station.

## On the project page

The project page shows the same tests under the HF band, and the past tests under them: the calls, the time in UTC and the dial of each, never the note.

The chat is not on the project page.

Not in this version: a test that repeats ("every Saturday": enter the weeks to come one by one), a reminder before a test, and tests on the map.
