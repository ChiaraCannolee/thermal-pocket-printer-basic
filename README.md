# crafts-and-co-thermal-pocket-printer-basic

Print to the **Crafts & Co 3128** thermal pocket printer directly from your computer via Bluetooth, no app required.

The Crafts & Co 3128 (sold at Action stores in the Netherlands/Europe) is a rebranded **DP-L1S** by Xiamen Print Future Technology, using the **LuckPrinter SDK**. Its companion app ("Luck Jingle") requires excessive permissions and a persistent internet connection for a device that prints over Bluetooth. This project removes the app from the equation.

## Quick start: Open the web app

**No installation needed.** Just open this in Chrome, Edge, or Opera:

**https://ChiaraCannolee.github.io/thermal-pocket-printer-basic/**

(Requires Web Bluetooth support – Chrome/Edge/Opera on desktop, not Firefox/Safari)

## What this does

- Connects to the printer over BLE from macOS or Linux
- Prints images, text, and test patterns
- Supports label/sticker paper, density control, and Floyd-Steinberg dithering for photos
- Provides a full command reference for the printer's BLE protocol

## Python CLI (for automation)
If you prefer command line or want to batch-process prints:

```bash
# Install dependencies
pip install bleak Pillow

# Print a test pattern
python3 print.py test

# Print an image
python3 print.py image photo.png

# Print with dithering (for photos/gradients)
python3 print.py image photo.png --dither

# Print text
python3 print.py text "Hello World"

# Print on sticker paper (label mode)
python3 print.py text "My Label" --label

# Check printer battery and status
python3 print.py info
```

## Web GUI vs CLI

The **web GUI** (`index.html`) is the easiest way to get started — no installation needed, just open in Chrome.

The **Python CLI** (`print.py`) is for automation, batch jobs, and integrations. Requires `pip install bleak Pillow`.

## Usage

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

## Compatible paper

The printer uses 56mm wide thermal sticker and label rolls (30mm label diameter). Compatible supplies include:

- Standard white thermal paper (included with printer)
- Crafts & Co clear glossy sticker rolls
- Crafts & Co white sticker rolls
- Crafts & Co coloured sticker rolls (pink, yellow, etc.)
- Standard 56mm thermal sticker/label rolls

The printer is "ink free": it uses heat to activate the thermal coating. Coloured papers just provide a coloured background under the black print.

## How it works

The printer communicates over BLE using a variant of the ESC/POS thermal printer protocol. The protocol was reverse-engineered from the decompiled Android APK and verified against hardware.

### Connection & Protocol

1. **Connect** to BLE service `ff00`, write to characteristic `ff02`, listen for notifications on `ff01`
2. **Advertise name**: printer broadcasts as "C&Co 3128_BLE" (note: no service UUIDs in advertisement)
3. **Enable printer**: send `10 FF F1 03` (Lujiang-specific command)
4. **Wake up**: send 12 null bytes
5. **Set density** (optional): `10 FF 10 00 [0|1|2]` for light/normal/dark
6. **Send bitmap**: GS v 0 raster image (384 pixels wide, 1-bit, MSB-first)
7. **Feed paper**: `1B 4A 50` (feed 80 dots)
8. **Stop job**: `10 FF F1 45` (wait for response)

For label/sticker paper with gap detection:
- Replace step 7 with `1D 0C` (position to next label)
- Use `1F 11 51` before print and `1F 11 50` after for position adjustment

See [PROTOCOL.md](PROTOCOL.md) for complete command reference.

## Compatible printers

This tool is confirmed to work with the Crafts & Co 3128 (DP-L1S). It will likely work with other printers from the LuckPrinter family that use the same SDK and `BaseNormalDevice` class; including various DP-/DP-series, LuckP-/LuckP-series, and MiniPocketPrinter models. The print width may differ (check with `print.py info`).

**Other printer classes use different enable/stop commands:**
For the Fichero D11s and other AiYin-based label printers, see [fichero-printer](https://github.com/0xMH/fichero-printer) by 0xMH, who reverse-engineered the same SDK for a different device class.

## Background

This project started as a privacy-motivated reverse-engineering exercise. The "Luck Jingle" app requires location permissions, internet access, and various other permissions that have no business being on a Bluetooth printer. The protocol was reverse-engineered by decompiling the Android APK with JADX and reading the `PrinterImageProcessor` and `BaseNormalDevice` classes from the LuckPrinter SDK.

## Licence

MIT
