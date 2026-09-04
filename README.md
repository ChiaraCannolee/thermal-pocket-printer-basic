# thermal-pocket-printer-basic

Print to a **DP-L1S** thermal pocket printer directly from your computer over Bluetooth, no app required.

The DP-L1S is a small thermal pocket printer made by Xiamen Print Future Technology, sold under various brand names (Crafts & Co 3128 in NL/EU via Craft & Co, Action stores, and others). Its companion app, "Luck Jingle", demands location permissions, a persistent internet connection, and a long list of other things that have no business being on a printer that just receives an image over Bluetooth from 30 cm away.

So I decompiled the Android APK with JADX, reverse-engineered the BLE protocol, and built a Python CLI and a web app that talk to the printer directly. No app, no account, no cloud.

## Quick start

**Web app (no install, just open in Chrome/Edge/Opera):**
**https://ChiaraCannolee.github.io/thermal-pocket-printer-basic/**

Web Bluetooth is required, so Firefox and Safari are out. Works on macOS and Linux. Windows is waiting on better Web Bluetooth support.

**Python CLI (for automation and batch jobs):**

```bash
pip install "bleak>=0.19" Pillow

python3 print.py test                         # test pattern
python3 print.py image photo.png --dither     # photo with Floyd-Steinberg
python3 print.py text "Hello World"
python3 print.py text "My Label" --label      # sticker/label paper mode
python3 print.py info                         # battery, firmware, model
```

## Features

- Print images, text, and test patterns
- Live preview of what comes out of the printer
- Three density levels
- Floyd-Steinberg dithering for photos and gradients
- Invert mode (swap black and white)
- Label mode for sticker paper with gap detection
- Battery indicator via BLE notifications

## How it works

The printer runs on the LuckPrinter SDK, which is used by 159+ printer models. The BLE protocol is an ESC/POS variant. The basic flow:

1. **Connect** to BLE service `ff00`, write to characteristic `ff02`, listen for notifications on `ff01`
2. **Enable printer**: send `10 FF F1 03` (Lujiang-specific command)
3. **Wake up**: send 12 null bytes
4. **Set density** (optional): `10 FF 10 00 [0|1|2]` for light/normal/dark
5. **Send bitmap**: GS v 0 raster image (384 pixels wide, 1-bit, MSB-first)
6. **Feed paper**: `1B 4A 50` (feed 80 dots)
7. **Stop job**: `10 FF F1 45` (wait for response)

For label/sticker paper with gap detection, replace step 6 with `1D 0C` (position to next label), and use `1F 11 51` before print and `1F 11 50` after for position adjustment.

The web version uses 100-byte chunks with 50ms delays because of Web Bluetooth's MTU limits. The Python CLI uses 512-byte chunks with 10ms delays, which is significantly faster.

The printer broadcasts as `C&Co 3128_BLE` and does not advertise its service UUIDs, so scanning by service filter alone won't find it.

See [PROTOCOL.md](PROTOCOL.md) for the complete command reference, including device info queries, status bitfield, and label/tattoo print sequences.

## CLI usage

```
python3 print.py <command> [options]

Commands:
  scan                  Scan for nearby BLE printers
  info                  Show printer info (model, battery, firmware)
  test                  Print a test pattern
  image <file>          Print an image (PNG, JPG, BMP, etc.)
  text <string>         Print text

Options:
  --address, -a         Printer BLE address (skip scanning)
  --density, -d 0|1|2   Print darkness (0=light, 1=normal, 2=dark)
  --dither              Floyd-Steinberg dithering (better for photos)
  --invert              Invert colours (white-on-black)
  --label               Label/sticker mode with gap detection
  --copies, -c N        Number of copies
  --width, -w N         Print width in pixels (default: 384)
  --feed, -f N          Paper feed after print in dots (default: 80)
```

## Compatible printers

Confirmed to work with the DP-L1S (sold as Crafts & Co 3128 and other rebrands). Will likely work with other printers in the LuckPrinter family that share the same SDK and `BaseNormalDevice` class — DP-/LuckP-/MiniPocketPrinter series and similar. Print width may differ; check with `python3 print.py info`.

For Fichero D11s and other AiYin-based label printers (different device class, same SDK), see [fichero-printer](https://github.com/0xMH/fichero-printer) by 0xMH.

## Compatible paper

The printer uses 56mm wide thermal paper and sticker rolls (30mm label diameter). It's "ink free": heat activates the thermal coating, so coloured papers just provide a coloured background under the black print.

## Troubleshooting

### Linux: `bleak.exc.BleakDBusError: [org.bluez.Error.NotAvailable] br-connection-profile-unavailable`

This one's a BlueZ quirk, not a bug in this repo, and you'll hit it on any Linux machine with this printer (or a rebrand of it).

The DP-L1S is a genuine dual-mode Bluetooth chip. It advertises two separate identities: a classic BR/EDR one (shows up in a scan without the `_BLE` suffix, describing itself as "imaging", a real classic Bluetooth service class historically used by printers and scanners) and the LE/GATT one this project actually talks to (`..._BLE`, "Miscellaneous"). `print.py` correctly scans over LE and connects to the `_BLE` address.

The failure happens a layer below this code, inside BlueZ itself. Bleak's Linux backend connects by calling BlueZ's generic `Device1.Connect()` D-Bus method with no transport hint. When BlueZ sees a device advertising as dual-mode, it tries the BR/EDR side first. This printer's classic side offers the old Basic Imaging Profile, and no mainstream Linux distro ships a BlueZ plugin for that anymore, so that negotiation fails before BlueZ ever reaches the plain GATT/LE connection Bleak actually asked for. BlueZ reports that failure back as `NotAvailable: br-connection-profile-unavailable`, and Bleak passes it straight through. See [hbldh/bleak#1521](https://github.com/hbldh/bleak/issues/1521) and [bluez/bluez#318](https://github.com/bluez/bluez/issues/318) for the same root cause reported against other dual-mode devices.

Two things to try, in order:

1. **Clear stale device state.** Costs nothing:

   ```bash
   bluetoothctl remove <the _BLE MAC address>
   ```

   then rerun `python3 print.py info`. If BlueZ cached this device from an earlier scan or pairing attempt in dual-mode form, a clean device object sometimes avoids re-triggering the BR/EDR attempt.

2. **Force the adapter into LE-only mode.** This is the actual fix, it stops BlueZ from ever attempting a BR/EDR connection on that adapter. In `/etc/bluetooth/main.conf`:

   ```ini
   [General]
   ControllerMode = le
   ```

   then `sudo systemctl restart bluetooth`.

   Caveat: this appears to be a global setting rather than per-adapter, so if that machine only has one Bluetooth radio, it disables classic Bluetooth entirely while active, including Bluetooth headphones/speakers, a classic BT mouse or keyboard, and car audio (anything LE-based, including most modern earbuds, is unaffected). If that's a dealbreaker, a cheap dedicated USB BLE dongle for just the printer sidesteps the tradeoff.

## Coming soon

I'm working on an expanded web version with:

- Adjustable label sizes with presets (29×12mm, 40×12mm, 50×30mm, 40×30mm, 48mm round, and custom)
- Save and load templates locally in the browser
- Drag text directly on the preview for free positioning
- Undo/redo
- Print preview screen with adjustable threshold, copies, density override, and post-print feed in mm

The basics in this repo are stable, so this version is being released first. The expanded version will get its own repo.

## Background

This project started as a privacy exercise. The "Luck Jingle" app requires location permissions, internet access, and various other permissions that have no business being on a Bluetooth printer. The protocol was reverse-engineered by decompiling the Android APK with JADX and reading the `PrinterImageProcessor` and `BaseNormalDevice` classes from the LuckPrinter SDK, then verified against hardware.

## Licence

MIT
