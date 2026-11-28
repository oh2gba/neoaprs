# Network access and the secure connection

## Opening the page from another device

By default the page answers on this computer only. To open it from another device on the same network, such as a laptop or phone at home while the radio and NeoAPRS run on a Raspberry Pi in the shack, tick **Allow access from the network** in the Settings tab, in the Web page group.

It counts at once, with no restart. The page now also listens on every interface (IPv4 and IPv6), on the same port. The group shows:

- the **access key**: three groups of four letters and digits, such as `k7m2-x9pq-4hrt`, made when the switch is first turned on;
- **Open on a phone**: a code to point a phone's camera at; it opens the page there, logged in ([On a phone](#on-a-phone)).

Another device, such as a laptop, opens `http://NAME.local:7303/` with the name of the computer, or the address the log says (`other devices open the page at ...`), and types the key into the one field of the key screen. The browser keeps the login for a year, so each device asks once. `neoaprs db get web/key` prints the key on a computer with no screen.

### On a phone

Point the phone's camera at the code and tap the link it shows. The page opens in the browser, logged in. The code holds the page's address with the key after `#`: the browser never sends that part to NeoAPRS, and the page takes it out of the address bar at once. If the key screen comes instead (the key was renewed since, or the code is a photo of an old one), type the key once.

Then put the page on the home screen, with the phone's own menu:

- **iPhone and iPad** (Safari): Share, *Add to Home Screen*, *Add*.
- **Android** (Chrome): the menu, *Add to home screen*, then *Add*, or *Install* where Chrome offers it.

The icon opens the address that was in the code, without the key. So:

- If the router gives the computer another address, the icon opens nothing: scan the code again and add it again. A DHCP reservation for the computer in the router keeps its address.
- Keep the default port: with `web/port` 0 the port changes at every start. With the secure connection on, the code has the secure port, 7304 unless that one is taken.
- A VPN on the computer that takes all its traffic (a full-tunnel WireGuard, for example) puts the VPN's address in the code, which the phone cannot open. Turn the VPN off while you scan, or open `http://NAME.local:7303/` on the phone.
- With the secure connection on and its certificate not installed on the phone, the browser warns first. Continue, and type the key if the key screen comes.
- If the icon on the home screen shows the key screen, type the key once there.

Switching the network off closes the pages that came in by it. On a page opened from another device, the page asks first ("This device will lose the page. Turn off?", Yes or Cancel).

The alert command runs on the NeoAPRS computer, and the page alerts in the browser it is open in ([notifications.md](notifications.md)).

A page on another device changes every setting but the ones that name a program or an address NeoAPRS runs or fetches from: the alert command (and its **Test**), `update/url`, `map/source` and `web/allowed_hosts`. It does not show them, and keeps the Notify me tickbox. On a computer without a screen set them there, for example `neoaprs db set messages/alert_command "LINE"`, then restart NeoAPRS.

### What is refused

- The page's files are free, because they hold the key screen. The connection that carries the data and the base map answer `401` to a device that has not logged in.
- This computer is never asked for a key: a page opened on it at `http://127.0.0.1:7303/` or `http://localhost:7303/`. The same computer at another of its names or addresses (its name, its address on the network) counts as from the network and gets the key screen; while **Allow access from the network** is off, it is sent to `http://127.0.0.1:7303/` instead.
- A reverse proxy on this computer is refused unless you allow it with `neoaprs db set web/proxy true`; then the address in its `X-Forwarded-For` is the visitor's, its `X-Forwarded-Proto: https` counts as the secure connection, and the visitor gets the key screen. A request counts as the proxy's when it sends `X-Forwarded-For`, `Forwarded`, `X-Real-Ip`, `X-Forwarded-Host`, `X-Forwarded-Proto` or `Via`; one that passes on the name the visitor typed (`proxy_set_header Host $host;`) gets the key screen too.
- A proxy that does neither, and asks for `127.0.0.1` itself, is this computer. nginx is such a proxy unless it is told otherwise, and whoever reaches it with a program of their own is not asked for a key. Tell it `proxy_set_header X-Forwarded-For $remote_addr;`.
- The page answers only to an IP address, `localhost`, the machine's own name (and `name.local`) and the names in the setting `web/allowed_hosts` (comma separated). A name for the machine that is not one of those is refused, and the log says so once with the command that adds it.
- **Wrong keys.** Five in a minute from one address shut that address out for five minutes, even for the right key. The log has every wrong key and the shutting out, and never the key.
- **A new key.** **New key** (it asks twice) makes another and logs every other device out: their open pages are closed and their sessions end at once. The device that pressed it stays in. A key you type yourself (`neoaprs db set web/key abcd-efgh-jkmn`, read when the daemon next starts) works the same. A key of your own must have the same form: three groups of four lowercase letters and digits without `0 1 i l o`.
- **The session** is a cookie (`neoaprs_session`, HttpOnly, SameSite=Strict) that holds an expiry, a random number and a signature of them under the key, not the key. The daemon stores nothing, a session survives a restart and ends with the key.

### Be careful

- **Plain HTTP.** The key is sent once, and the session cookie with every request, in the clear. Use it on a network you trust. Reach the Pi from outside through a VPN, not by opening the port to the internet. Do not forward a port to NeoAPRS in your router.
- Whoever is logged in can work the radio and change the other settings. The key is the only lock, so give it to your own devices only.
- **Windows** asks whether to let NeoAPRS through its firewall the first time the switch is on. Allow it on private networks.

### Another port

The page is on port 7303 (`web/port`, not on the page; `neoaprs db set web/port N`). `--web-port N` takes another one for a single run, and 0 takes a free one at once. A port that is in use moves the page to the first free one of the ten after it, and the log says which (`web page at http://127.0.0.1:PORT/`). When none is free the daemon runs without the page.

## The secure connection (https)

Tick **Secure connection (https)**, with **Allow access from the network**, in the same group. It is off by default. It is what a phone needs for notifications and what installing the page as an app needs, apart from `localhost`.

- NeoAPRS makes its own small certificate authority, "NeoAPRS local CA", and a certificate of this computer that it signs. They are made once, in `tls/` of the data folder (readable only by you), and renewed by themselves. The authority lasts ten years and is made only once, so a device that has trusted it stays trusted.
- The authority can sign only for this computer: its name, `localhost`, the names ending in `.local`, the names in `web/allowed_hosts` and the addresses it had when the authority was made, and the addresses of a home or local network. Its key could not be used for any other site. A name given to the computer later is left out of its certificate, and the log says which.
- An authority made by an earlier version has no such limit and keeps working. To have one of the limited kind, stop NeoAPRS, move the folder `tls/` of the data folder away and start it: each device then trusts the new authority once. The computer's certificate lasts at most 800 days and is made again when it has less than 30 days left, or when the computer has a name or address it does not name.
- The page and its socket are served over TLS on the port after the plain one (7304 for 7303; if that is taken, the next free one of the ten after it). The plain port stays open.
- A device other than this computer that asks the plain port is sent on to the secure one. `localhost` keeps plain http; on the computer itself http is already a secure address for the browser, and the desktop app's window is there.
- If the secure side cannot start, the page says why and the plain port goes on as it was.
- A secure session cookie is marked secure.

Browsers show a warning the first time, because they do not know the authority. You can continue past it, or make the warning go away by installing the authority's certificate on the device. The certificate is the file `NeoAPRS-CA.crt`, downloaded from `/neoaprs-ca.crt` on either port (only the public certificate, never a key). A guide under the switch lists the steps for Android, iPhone and iPad, Windows, macOS, Linux (Chrome) and Firefox, for the device you are on.

## Install the page as an app

The page can be installed so that it opens in a window of its own with an icon. Once opened, its shell opens even while the daemon is away; it then says "daemon offline" and connects when the daemon is back.

A browser installs a page only from a secure address: `http://127.0.0.1:7303/` or `http://localhost:7303/` on the computer that runs NeoAPRS, an `https://` address (the secure connection above, or a reverse proxy in front of the daemon with its host name in `web/allowed_hosts`).

- **On the computer that runs NeoAPRS** (Chrome, Edge, Brave, Opera): open the page, then use the install icon at the end of the address bar, the browser's menu ("Install NeoAPRS…"), or **Install app** in the Settings tab, In this browser, which is there when the browser offers the install. Firefox and Safari on a computer do not install pages. The [desktop app](desktop.md) is a window of its own already.
- **On a phone over plain `http://`** the browser refuses the install, and the page works as before with no message. A phone can still put it on the home screen ([On a phone](#on-a-phone)); the icon needs the daemon to be reachable, as the page does in a tab. With the secure connection on and the certificate installed, a phone can install the page.
- **What the browser keeps.** The page's numbered files are kept after their first use. The shell, the manifest, the icons, the symbol sheets and the glyph files are asked of the daemon every time, and a kept copy is shown only when the daemon cannot be reached, so an update is never hidden behind an old page. The data connection, the login, the base map and everything that is not a plain read are never kept. A new release brings a new helper that takes over at once and deletes the old files. To clear it: the browser's site settings, *Clear data* for the address.
