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
pip install bleak Pillow

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
