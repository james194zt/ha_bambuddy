# Bambuddy Panel for Home Assistant

Put [Bambuddy](https://github.com/maziggy/bambuddy) inside Home Assistant: a sidebar entry that shows the full Bambuddy app, with its live camera, plus Bambuddy's notifications on your phone, with camera snapshots. Both work at home and away, including in the Home Assistant Companion app over Nabu Casa or any other https remote access.

It's made for Bambu Lab printers in **LAN mode**, where Bambu Handy can't reach the printer. Home Assistant becomes your secure way in to Bambuddy from anywhere.

## Features

- **Sidebar panel.** Bambuddy opens in Home Assistant's main window next to the sidebar, like an add-on such as AdGuard. On phones, a slim header with the ☰ button lets you open the sidebar.
- **Works remotely.** Home Assistant serves Bambuddy itself, so it goes wherever Home Assistant goes. Bambuddy never has to be exposed to the internet.
- **Everything works.** Printer status, live updates, the embedded camera stream, archives, the queue and settings all work inside the panel.
- **Secured by your Home Assistant login.** Nobody can open Bambuddy through Home Assistant without being logged in to Home Assistant.
- **Phone notifications with snapshots.** The `bambuddy_panel.notify` service passes Bambuddy's alerts to the Companion app. Camera snapshots load through Home Assistant, so they show on mobile data too. Tapping a notification opens the Bambuddy panel.
- **Fast on mobile data.** Bambuddy's large app bundle is compressed on the way through.

## Requirements

- Home Assistant 2024.12 or newer. Tested on 2026.9.4.
- Bambuddy running somewhere Home Assistant can reach on your network, e.g. `http://192.168.1.1:8000`.
- For notifications: the Home Assistant Companion app on your phone, signed in to your Home Assistant.

## Install

1. In Home Assistant, open **HACS** → ⋮ (top right) → **Custom repositories**.
2. Add `https://github.com/james194zt/ha_bambuddy` with type **Integration**.
3. Search HACS for **Bambuddy Panel**, open it and click **Download**.
4. Restart Home Assistant: **Settings** → **System** → ⏻ (top right) → **Restart Home Assistant**.
5. Go to **Settings** → **Devices & services** → **Add integration**, search for **Bambuddy Panel** and fill in the form (see below).

## Configure

| Setting | What to enter | Example |
|---|---|---|
| **Bambuddy URL** | The address Home Assistant uses to reach Bambuddy on your network. | `http://192.168.1.1:8000` |
| **Sidebar title** | The name shown in the sidebar. | `Bambuddy` |
| **Sidebar icon** | Any Material Design icon. | `mdi:printer-3d` |
| **Notification phones** | Optional. The phones that get Bambuddy's notifications (see the next section). | `notify.mobile_app_my_phone` |

To change these settings later, go to **Settings** → **Devices & services** → **Bambuddy Panel** → **Configure**.

After installing, **Bambuddy** appears in the sidebar. Open it on desktop and in the Companion app to check it loads.

## Set up phone notifications

Bambuddy has a built-in Home Assistant notification provider. Point it at this integration's `bambuddy_panel.notify` service, and the integration sends each notification to the phones you choose.

> **Why not send straight to `notify.mobile_app_…`?** Bambuddy builds snapshot links from its own network address, e.g. `http://192.168.1.1:8000/…`. Your phone can only open that link on your home Wi-Fi, so away from home the picture is missing. `bambuddy_panel.notify` changes the link so the picture loads through Home Assistant with your login, wherever you are.

### Step 1: Check Bambuddy is connected to Home Assistant

Bambuddy sends notifications by calling Home Assistant, so it needs its own connection to Home Assistant.

1. In Bambuddy, go to **Settings** → **Network**.
2. Under **Home Assistant**, fill in:
   - **Home Assistant URL:** your Home Assistant address on your network, e.g. `http://192.168.1.10:8123`.
   - **Token:** a long-lived access token. To create one in Home Assistant, click your **profile** (bottom left) → **Security** → **Long-lived access tokens** → **Create token**.
3. Still under **Settings** → **Network**, make sure **External URL** is filled in. Bambuddy only attaches snapshots when it's set. Its own network address is fine, e.g. `http://192.168.1.1:8000`.
4. Click **Save**.

### Step 2: Pick your phone(s) in Home Assistant

1. Go to **Settings** → **Devices & services** → **Bambuddy Panel** → **Configure**.
2. Under **Notification phones**, select each phone that should get notifications, e.g. `notify.mobile_app_my_phone`. Each phone with the Companion app appears as `notify.mobile_app_<phone name>`.
3. Click **Submit**.

### Step 3: Add the notification provider in Bambuddy

1. In Bambuddy, go to **Settings** → **Notifications** → **Add Provider**.
2. Fill in:
   - **Provider Type:** `Home Assistant`
   - **Name:** anything, e.g. `HA - My phone`
   - **Service:** `bambuddy_panel.notify`. Use exactly this, not your phone's `notify.mobile_app_…` service.
   - **Data:** leave empty, or see [Extra options](#extra-options).
   - **Attach Photo:** on
3. Under **Notification Events**, tick what you want to hear about. A good set to start with:
   - **Print Completed**, **Print Failed**, **Print Stopped**
   - **First Layer Complete** (sends a snapshot of the first layer)
   - **Printer Error**, **Printer Offline**
   - **Plate Not Empty**
   - **AI Failure Detection**, if you use Obico
4. Click **Save**.

### Step 4: Test it

1. On your phone, **turn off Wi-Fi**, so the test proves it works away from home.
2. In Bambuddy, open the provider and click **Send Test Notification**.
3. Within a few seconds you should get a notification titled **Bambuddy Test**, with a picture. For the test, the picture is the Bambuddy logo; real events attach a camera snapshot.
4. Tap the notification. The Companion app should open on the Bambuddy panel.

If nothing arrives, see [Troubleshooting](#troubleshooting).

### Extra options

Anything you put in the provider's **Data** field is passed to the phone unchanged. For example:

- `{"priority": "high", "ttl": 0}`: deliver immediately on Android, even when the phone is idle.
- `{"channel": "Bambuddy"}`: give Bambuddy its own Android notification channel, so you can set its sound and importance separately.
- `{"push": {"sound": "default"}}`: play a sound on iOS.

You can also call the service yourself from automations or scripts:

```yaml
action: bambuddy_panel.notify
data:
  title: Printer
  message: Remember to clear the plate
```

## How it works

- **Proxy:** Home Assistant serves Bambuddy under `/api/bambuddy_panel/proxy/`, including pages, the API, live updates and camera streams.
- **Login:** the panel swaps your Home Assistant login for a signed, HTTP-only session cookie that only applies to that path. The Companion app's own Home Assistant login is also accepted, which is how notification snapshots load. Anything else gets `401 Unauthorized`. The cookie signing key is stored in `.storage/bambuddy_panel.secret`.
- **Path rewriting:** Bambuddy expects to run at the root of its own server. The proxy rewrites absolute paths in its HTML and CSS, gives its router a base path, and adds a small script (`shim.js`) for URLs the app builds while running. It also removes the headers that stop Bambuddy being shown inside another page.
- **Service worker:** Bambuddy's offline service worker is turned off inside Home Assistant, because it would take over Home Assistant's own address.

## Troubleshooting

- **The panel says "Open Bambuddy from the Home Assistant sidebar."** The page was opened directly instead of through the panel. Open **Bambuddy** from the sidebar.
- **Blank panel, or "Bambuddy unreachable".** Check that Home Assistant can reach the **Bambuddy URL** in the integration's settings.
- **No notification at all.**
  - In Bambuddy, check **Settings** → **Notifications** shows the provider as enabled, and that the test reported success.
  - In Home Assistant, check **Settings** → **System** → **Logs**. "No phones selected" means step 2 wasn't saved.
- **Notification arrives but without a picture.**
  - Check **Attach Photo** is on and Bambuddy's **External URL** is set (step 1).
  - Make sure the provider's **Service** is `bambuddy_panel.notify`, not `notify.mobile_app_…`.
- **Bambuddy updated and something in the panel broke.** Bambuddy may have changed how it builds its pages. Please open an issue.

**Known limits:**
- A few Bambuddy actions reload the whole page, such as the **Projects** link in the archive menu. On older browsers (e.g. older Safari), these can land on Home Assistant instead of Bambuddy. If that happens, open the panel again from the sidebar.
- Bambuddy's camera **Window** view mode opens a separate window. In the Companion app that window may open in your phone's browser, which isn't logged in. Use the **Embedded** camera view mode instead.

## Development

The tests run the integration in a real Home Assistant test instance against a fake Bambuddy:

```bash
pip install pytest-homeassistant-custom-component
pytest
```
