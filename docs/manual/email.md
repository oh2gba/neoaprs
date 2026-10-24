# Email

The APRS email gateway is the APRS-IS station `EMAIL-2` ([aprs-is.net/Email.aspx](http://aprs-is.net/Email.aspx)). The Email tab sends mail through it and lists what it sent back.

## How it works

The gateway is on the internet, not on the radio. A mail reaches it through an iGate that hears your radio and puts the packet on the internet. Its acks and answers come back through an iGate within reach of your radio that puts them on the air. With no iGate in reach nothing gets through, and a mail that did get through can still look unanswered.

A mail is an ordinary numbered message to `EMAIL-2`. Its text is the address, a space and the text, one line of at most 67 bytes in all. `jane@example.com Hello Pekka` is a mail, so the address and the space take their share of the 67.

The gateway serves interactive stations only and blocks a station that sends in the blind. NeoAPRS is interactive: a person types each message.

The gateway gets two attempts, not four, because its acks rarely reach you ([messages.md](messages.md#attempts)). A mail that was sent twice with no ack is *Not confirmed*, which is not a failure.

## The Email tab

The tab is a mail list, not a conversation. It has one row for each message to or from the gateway, the oldest first and scrolled to the newest at the bottom, as the Messages tab is, with no bubbles. The list fills the tab between the top and the box to write in.

**At the top** is the button **Check email** and a small (i): mail goes through the gateway and an iGate, so it may show "Not confirmed" although it arrived, and Check email asks the gateway for the mail it kept for you (24 hours).

- Check email asks the gateway to send again the mail it kept for you. The list shows a row "Checked email" with its state.
- It is off while the TNC is not connected, and it says "Already checking" while an earlier question is still being sent, so the gateway is not asked twice.

**At the bottom**, always there, is the box for a mail:

- **To** is an email address. While the box has the focus, the addresses used before that match what you typed are listed under it, opening upward over the list, newest first. A click picks one, and the trash can beside it forgets it. The addresses are kept in your browser. **Esc** closes that list; with none open, it clears the address and the text being written.
- **Text** and "N left", the characters left of the 67 over the address, the space and the text.
- **Send** at the lower right. It is off while the TNC is not connected, the address or the text is empty, the address has a space in it, or the line is more than 67 bytes. After Send the text is empty again and the address stays, for the next mail to the same person.

## The rows

A mail of yours is "To jane@example.com" over its text, in one line. A click on the row opens it to show the whole text, the date and time, the route and the chain of digipeaters of its latest attempt. Under it are the time and its state in words, with its mark:

| state | mark | meaning |
|---|---|---|
| Waiting for the radio | clock | before the first attempt |
| Sending (1 of 2) | clock | the attempt out of the 2 the gateway is given |
| Delivered | check | the gateway acked it |
| Not confirmed | hollow check | sent twice with no ack; the gateway may well have the mail. A late ack still settles it |
| Rejected | cross | the gateway rejected it |
| Cancelled | dash | you stopped it |

- **Retry** (for a mail that is not confirmed, rejected or cancelled; it may mean twice to the gateway) and **Cancel** (while it is being sent) are small buttons on the row.
- The trash can in the row's corner deletes it after a second press ("sure?"); the row goes from every page.
- What the gateway sent is "From EMAIL-2" over its text. When its text starts with an email address and a blank (`jane@example.com Hello`, also `<jane@example.com> Hello` or `jane@example.com: Hello`), the row is taken for mail that the gateway forwards to you and reads "From jane@example.com" over the rest.
- The gateway's acks are no rows. They settle the state of the mail they belong to.
- A row that came in while the Email tab was not on show is bold with a bar at its left, until the tab has been left and is opened again.

The tab's badge counts the messages from `EMAIL-2` not seen, under the same rules as the Messages tab's: the Email tab on show, the panel open, the page visible. The title of the browser tab counts both tabs.

`EMAIL-2` is not among the conversations of the Messages tab and its messages are not in that tab's count. The Message button on the gateway's station card opens the Email tab.

## Shortcuts at the gateway

The gateway has its own shortcut commands, which the page does not use: it sends to addresses. A name that is already a shortcut of your call at the gateway still works when typed in **To**. The page shows a shortcut command in the history as the plain mail it is on the wire.

- A shortcut is a name for an address, made by sending the address once with the name in front, `me jane@example.com`, and used from then on as the addressee, `me Hello`. A name is letters and digits and belongs to the call that made it.
- Only the people who are shortcuts of a call can email that call. Their mail arrives as an APRS message from `EMAIL-2` (they put `CALLSIGN-SSID:` first in the subject).
- `name L` makes the gateway email the list of the call's shortcuts to that shortcut's address, and `name R` removes it.
- `get` fetches the mail the gateway holds for you. Mail from a shortcut that your radio did not acknowledge (4 tries, a minute apart) is held for 24 hours, and `get` makes the gateway send all of it, 10 seconds apart. Check email sends `get`.
- The gateway's acks and status replies come back as ordinary messages from `EMAIL-2`, through an iGate that puts them on the air as third-party frames.
