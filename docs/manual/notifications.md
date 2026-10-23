# Being told of a new message

A new message can alert you in two places, and both are in the **Notifications** group of the Settings tab:

- **On the NeoAPRS computer:** the daemon runs a command of yours.
- **In this browser:** the page alerts by itself, in whatever browser has it open.

Both alert for the same messages: a message to you, the first copy only. Not a bulletin or a group message, an ack, a reject, a query that NeoAPRS answers, a message you only overheard, or one of your own. A repeat of a retry or another digipeater's copy does not alert again.

## On the NeoAPRS computer

When a message to you arrives and **Alert** (`messages/alert`) is on, which it is by default, NeoAPRS runs the shell line in **Command** (`messages/alert_command`, at most 1000 characters; empty runs nothing). The default on Linux is a notification and a sound:

```
(notify-send -- "APRS message from $NEOAPRS_FROM" "$NEOAPRS_TEXT" 2>/dev/null || kdialog --title "APRS message from $NEOAPRS_FROM" --passivepopup "$NEOAPRS_TEXT" 10); paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga
```

The command gets these in its environment:

| variable | what it holds |
|---|---|
| `NEOAPRS_FROM` | the sender's call |
| `NEOAPRS_TEXT` | the text |
| `NEOAPRS_AT` | when it was heard, ISO 8601 in UTC (`2026-10-21T12:00:00Z`) |
| `NEOAPRS_MSG_ID` | the id the sender gave it; empty when it had none |

The text is in the environment and not in the command line, so what a stranger wrote is never read as shell. Quote the variables in your own command.

- The command gets 20 seconds and is then killed with everything it started (60 seconds on Windows). Its output is in the log at debug level.
- A command that fails (it cannot start, exits with a status other than 0, runs out of time) is a warning in the log once an hour and a debug line otherwise. It never touches the daemon.
- Its environment is not the daemon's: only the names a program needs to find the desktop (`PATH`, `HOME`, `DISPLAY`, `WAYLAND_DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, `XDG_*` ...) and the four variables above. The service unit sets `DBUS_SESSION_BUS_ADDRESS` so that `notify-send` finds the desktop from a user service.
- At most 5 alerts run at once; more are dropped.

**On Windows** the command is a PowerShell script. Read the variables as `$env:NEOAPRS_FROM` and `$env:NEOAPRS_TEXT`. A step that fails ends the script with status 1, and `exit N` gives its own status. The default is a PowerShell toast with the sender and the text, and the system's sound.

**The Test button** to the right of the Command field runs the command as it is saved, exactly as for a real message. `NEOAPRS_FROM` is `NEOAPRS`, `NEOAPRS_TEXT` is `This is a test of the NeoAPRS alert`, `NEOAPRS_AT` is now and `NEOAPRS_MSG_ID` is empty. It works whatever **Alert** says.

The answer is shown under the field until the next edit: green `ran` when it worked, else red with the exit code and the first line of stderr (`exit code 3: no display`), or that it could not start or was killed. An empty command answers `no alert command`. The button waits while a test runs, and is off, with the title "Save first", while the field differs from the saved command.

## In this browser

The command runs on the computer the daemon runs on, which is not where you are when NeoAPRS is a service on a Raspberry Pi and the page is open on a laptop or a phone. So the page alerts by itself, once for each message that arrives while the page is open, in a background tab too. What the page loaded with, and what it is told again after a reconnect, is not new.

**Alert for a new message** is one choice, kept in this browser and not on the daemon, so each device decides:

| choice | what a new message does |
|---|---|
| **off** | nothing |
| **sound** | a short chime (made by the page, no sound file) and, while the page is hidden or not in focus, the alert of the browser tab: its title alternates between "✉ OH2DPN" and the usual one and its icon has a dot, until the page is seen again. The count of messages not seen stays in the title |
| **sound and pop-up** | the chime and a pop-up of the browser, "APRS message from OH2DPN" with the text. A click on it brings the page to the front and opens that conversation. Where no pop-up is shown after all (no permission, or the browser refuses), the tab alert takes its place |
| **pop-up only** | the pop-up without the chime, and the tab alert where it cannot be shown |

- A page opened from another device starts at **sound and pop-up** where the browser can show pop-ups, else at **sound**.
- A page on the computer itself (`localhost`, `127.0.0.1`, `[::1]` and the desktop app), where the command already notifies, starts at **off**, so that nothing alerts twice.
- The two choices with a pop-up are off, with the reason as their hover title, where the browser cannot show one: "Pop-ups are off in this browser for this address" or "Pop-ups are blocked for this page in the browser".
- Where the reason is the address (a page opened over plain http from another computer), **Enable pop-ups…** stands beside the choice and opens the steps for your browser, inside the page ([below](#pop-ups-need-a-secure-address)).
- Choosing one is the click that asks the browser for the permission. The page never asks by itself. When it is refused the choice goes back to **sound** and the words "pop-ups refused: sound only" stand beside it. "pop-ups not allowed yet" or "pop-ups blocked" next to the choice say that a pop-up is chosen but the permission is not there.
- A browser lets a page make a sound only after you have clicked or pressed a key in it, so the chime is silent until then and the tab alert is all there is.

Each test beside the choice works whatever the choice is and says for a few seconds what happened:

| button | what it does | words after it |
|---|---|---|
| **Test sound** | plays the chime now | `played`; `sound locked: click the page once` when the browser will not let the audio run yet |
| **Test pop-up** | shows a pop-up now, "APRS message from NEOAPRS", asking for the permission first if the browser has not been asked. Where none can be shown it flashes the browser tab for a few seconds | `pop-up sent`; `pop-up blocked` when the permission is refused or the browser will not show it; `pop-ups are off for this address` with **Enable pop-ups…** beside it |
| **Test** (on the NeoAPRS computer) | runs the alert command as it is saved | the command's result, under its field |

### Pop-ups need a secure address

Browsers show pop-ups only on `localhost`, over HTTPS, or at an address you have told the browser to treat as secure. A page opened at `http://<pi-address>:7303` is not one. Two ways out:

- Switch on the secure connection ([network.md](network.md#the-secure-connection-https)), and install NeoAPRS's certificate on the device, or continue past the browser's warning.
- Tell the browser to treat the address as secure. **Enable pop-ups…** shows these steps in the page, for the browser in use, with the host or the address ready to copy.

1. **Firefox** (a computer): open a new tab, type `about:config`, press Enter and click "Accept the Risk and Continue". Search for `dom.securecontext.allowlist`. If it is not there choose "String", click "+", put in the host name or address alone, without the port (`neoaprs-pi.local` or `192.168.1.20`) and click the tick. If it has text already, add a comma and the host at the end. Come back to the page and reload it.
2. **Chrome, Edge, Brave and Opera** (a computer): paste `chrome://flags/#unsafely-treat-insecure-origin-as-secure` (`edge://flags/...`, `brave://flags/...`, `opera://flags/...`) in the address bar. A page cannot open it for you. In the box put the origin of the page with its port (`http://192.168.1.20:7303`), set the choice to Enabled, click Relaunch, and reload the page.
3. **On a phone** the sound and the tab alert work. Pop-ups need HTTPS (and many phone browsers want a service worker for them), which a page served on plain http does not have.

After the reload, the two choices with a pop-up are there and **Test pop-up** works. Choose **sound and pop-up** and answer the browser's question.

### Pop-ups do not appear?

When Test pop-up says `pop-up sent` and nothing shows, the browser has handed the pop-up on and something outside the page holds it back. Look at, in this order:

1. the site's permission in the browser (the padlock of the address bar: notifications must be Allow);
2. the desktop's do-not-disturb or focus mode;
3. for **Firefox installed as a Flatpak on KDE Plasma**, the desktop portal. Firefox hands its pop-ups to it, and the KDE portal accepts them and never shows them (seen with Plasma 6.3).

The cure for the portal is to let Firefox talk to the notification service itself and tell it not to use the portal, then restart Firefox:

```
flatpak override --user --talk-name=org.freedesktop.Notifications org.mozilla.firefox
flatpak override --user --env=NOTIFY_IGNORE_PORTAL=1 org.mozilla.firefox
```

`neoaprs doctor` checks this and prints the two commands when the overrides are missing; it only reads them. To undo it: `flatpak override --user --no-talk-name=org.freedesktop.Notifications org.mozilla.firefox` and `flatpak override --user --unset-env=NOTIFY_IGNORE_PORTAL org.mozilla.firefox`. A browser from the system's own packages does not go through the portal.

## When no page is open

The page alerts only while it is open somewhere. To be told when no page is, make the alert command push to your phone. For example, with the [ntfy](https://ntfy.sh/) app subscribed to a topic, the command can be:

```
curl -s -H "Title: APRS message from $NEOAPRS_FROM" -d "$NEOAPRS_TEXT" https://ntfy.sh/<your-random-topic>
```

An ntfy.sh topic is public to whoever guesses its name, so make it long and random, or run your own ntfy server. What a message says goes through that server.
