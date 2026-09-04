#!/usr/bin/env python3
"""
crafts-and-co-printer: Print to Crafts & Co 3128 (and compatible LuckPrinter
thermal printers) directly from your computer via BLE, no app required.

Usage:
  python3 print.py test                        Print a test pattern
  python3 print.py image photo.png             Print an image file
  python3 print.py image logo.png --dither     Print with Floyd-Steinberg dithering
  python3 print.py image art.png --invert      Invert colours (white on black)
  python3 print.py text "Hello World"          Print text
  python3 print.py text "Label" --label        Print on label/sticker paper
  python3 print.py info                        Show printer info (battery, firmware, etc.)
  python3 print.py scan                        Scan for nearby BLE printers

Options:
  --address XX:XX:XX:XX:XX:XX   Skip scanning, connect directly
  --density 0|1|2               Print darkness (0=light, 1=normal, 2=dark)
  --dither                      Use Floyd-Steinberg dithering (better for photos)
  --invert                      Invert image (swap black/white)
  --label                       Use label/sticker mode (gap detection)
  --width N                     Print width in pixels (default: 384)
  --feed N                      Paper feed after print in dots (default: 80)
  --copies N                    Number of copies (default: 1)

Requirements:
  pip install bleak Pillow

Based on reverse-engineered LuckPrinter SDK (com.luckprinter.sdk_new).
See PROTOCOL.md for full protocol documentation.
"""

import argparse
import asyncio
import sys

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    print("Missing dependency: bleak")
    print("Install with: pip install bleak")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Missing dependency: Pillow")
    print("Install with: pip install Pillow")
    sys.exit(1)


# ── BLE constants ────────────────────────────────────────────────────

SERVICE_UUID     = "0000ff00-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID  = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"

DEFAULT_WIDTH  = 384
DEFAULT_FEED   = 80
CHUNK_SIZE     = 512
CHUNK_DELAY    = 0.01

SCAN_KEYWORDS = ["C&CO", "3128", "L1S", "LUCK", "LJ", "DP-", "CRAFTS"]


# ── Notification handling ────────────────────────────────────────────

received_data = []

def notification_handler(sender, data):
    received_data.append(data)


def get_response_text():
    """Extract ASCII text from received notifications."""
    for d in received_data:
        try:
            text = d.decode('ascii', errors='ignore').strip('\x00')
            if text:
                return text
        except:
            pass
    return None


# ── Image processing ─────────────────────────────────────────────────

def floyd_steinberg_dither(img):
    """
    Apply Floyd-Steinberg dithering to a grayscale image.
    Returns a 1-bit image with much better tonal reproduction than
    simple thresholding. Ported from the LuckPrinter SDK.
    """
    img = img.convert('L')
    width, height = img.size
    pixels = [float(img.getpixel((x, y))) for y in range(height) for x in range(width)]

    for y in range(height):
        for x in range(width):
            idx = y * width + x
            old_val = pixels[idx]
            new_val = 255.0 if old_val >= 128 else 0.0
            pixels[idx] = new_val
            error = old_val - new_val

            if x + 1 < width:
                pixels[idx + 1] += error * 7 / 16
            if y + 1 < height:
                if x > 0:
                    pixels[(y + 1) * width + (x - 1)] += error * 3 / 16
                pixels[(y + 1) * width + x] += error * 5 / 16
                if x + 1 < width:
                    pixels[(y + 1) * width + (x + 1)] += error * 1 / 16

    result = Image.new('L', (width, height))
    for y in range(height):
        for x in range(width):
            val = max(0, min(255, int(pixels[y * width + x])))
            result.putpixel((x, y), val)

    return result


def prepare_image(source, width_px=DEFAULT_WIDTH, dither=False, invert=False):
    """
    Convert an image to the correct size and format for printing.
    Returns a grayscale PIL Image ready for bitmap conversion.
    """
    if isinstance(source, str):
        img = Image.open(source)
    else:
        img = source

    # Convert to grayscale
    img = img.convert('L')

    # Resize to print width
    if img.width != width_px:
        ratio = width_px / img.width
        new_height = int(img.height * ratio)
        img = img.resize((width_px, new_height), Image.LANCZOS)

    # Invert if requested
    if invert:
        from PIL import ImageOps
        img = ImageOps.invert(img)

    # Apply dithering
    if dither:
        img = floyd_steinberg_dither(img)

    return img


def _pixel_data(img):
    """Get flat pixel values from a grayscale image, across Pillow versions.

    Image.getdata() is deprecated as of Pillow 12 in favour of
    get_flattened_data() and is slated for removal in Pillow 14
    (2027-10-15). Use the new method where it exists, fall back to the old
    one on older Pillow installs that don't have it yet.
    """
    if hasattr(img, 'get_flattened_data'):
        return img.get_flattened_data()
    return list(img.getdata())


def image_to_bitmap(img, width_px=DEFAULT_WIDTH):
    """
    Convert a grayscale PIL Image to 1-bit bitmap bytes.
    Returns (bitmap_bytes, width_bytes, height_px).
    """
    width_bytes = (width_px + 7) // 8
    height_px = img.height
    pixels = _pixel_data(img)

    bitmap = bytearray(width_bytes * height_px)

    for y in range(height_px):
        for xb in range(width_bytes):
            byte_val = 0
            for bit in range(8):
                x = xb * 8 + bit
                if x < width_px:
                    if pixels[y * width_px + x] < 128:
                        byte_val |= (128 >> bit)
            bitmap[y * width_bytes + xb] = byte_val

    return bytes(bitmap), width_bytes, height_px


def create_test_image(width_px=DEFAULT_WIDTH):
    """Generate a test pattern image."""
    height = 200
    img = Image.new('L', (width_px, height), 255)
    draw = ImageDraw.Draw(img)

    # Border
    draw.rectangle([0, 0, width_px - 1, height - 1], outline=0, width=2)

    # Text
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except:
            font = ImageFont.load_default()
            font_sm = font

    draw.text((width_px // 2, 25), "TEST PRINT", anchor="mt", fill=0, font=font)
    draw.text((width_px // 2, 75), f"{width_px}px wide", anchor="mt", fill=0, font=font)

    # Gradient bar (for dithering test)
    for x in range(20, width_px - 20):
        grey = int((x - 20) / (width_px - 40) * 255)
        draw.line([(x, 120), (x, 150)], fill=grey)
    draw.text((width_px // 2, 155), "gradient (use --dither for smooth)", anchor="mt", fill=0, font=font_sm)

    # Alignment marks
    draw.line([(10, 10), (width_px - 10, 10)], fill=0, width=1)
    draw.line([(10, height - 10), (width_px - 10, height - 10)], fill=0, width=1)
    draw.line([(10, 10), (10, height - 10)], fill=0, width=1)
    draw.line([(width_px - 10, 10), (width_px - 10, height - 10)], fill=0, width=1)

    # Checkerboard
    for cy in range(165, 195, 4):
        for cx in range(10, 50, 4):
            if ((cx + cy) // 4) % 2 == 0:
                draw.rectangle([cx, cy, cx + 3, cy + 3], fill=0)

    return img


def create_text_image(text, width_px=DEFAULT_WIDTH, font_size=48):
    """Render text as an image for printing."""
    # Try to find a good font
    fonts_to_try = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFCompact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]

    font = None
    for font_path in fonts_to_try:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Measure text
    dummy = Image.new('L', (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Handle multi-line and wrapping
    padding = 20
    img_height = text_h + padding * 2

    img = Image.new('L', (width_px, img_height), 255)
    draw = ImageDraw.Draw(img)

    x = (width_px - text_w) // 2
    y = padding
    draw.text((x, y), text, fill=0, font=font)

    return img


# ── Protocol commands ─────────────────────────────────────────────────

def build_gs_v_0(bitmap_data, width_bytes, height_px, mode=0):
    """Build ESC/POS GS v 0 raster image command."""
    header = bytes([
        0x1D, 0x76, 0x30,
        mode & 0x03,
        width_bytes % 256,
        width_bytes // 256,
        height_px % 256,
        height_px // 256,
    ])
    return header + bitmap_data


# ── BLE communication ─────────────────────────────────────────────────

async def ble_send_chunked(client, data, label="data"):
    """Send data in BLE-sized chunks.

    CHUNK_SIZE (512) is an upper bound, not a guarantee: it only works if
    the connection actually negotiated a large enough ATT MTU. Writing more
    than that in one write-without-response call makes BlueZ reject it
    outright with "org.bluez.Error.Failed: Failed to initiate write" rather
    than trimming it, so we cap to what the characteristic actually reports
    it can take.
    """
    chunk_size = CHUNK_SIZE
    char = client.services.get_characteristic(WRITE_CHAR_UUID)
    if char is not None:
        # BlueZ reports the ATT minimum (20 bytes) until MTU negotiation
        # with the printer finishes, which can take a moment after connect,
        # and on BlueZ < 5.62 it never reports anything else. Give it a
        # little time to settle on a bigger value; if it doesn't, we just
        # chunk smaller instead of sending an oversized write.
        for _ in range(20):
            if char.max_write_without_response_size > 20:
                break
            await asyncio.sleep(0.1)
        chunk_size = min(CHUNK_SIZE, char.max_write_without_response_size)

    total = len(data)
    sent = 0
    while sent < total:
        chunk = data[sent:sent + chunk_size]
        await client.write_gatt_char(WRITE_CHAR_UUID, chunk, response=False)
        sent += len(chunk)
        await asyncio.sleep(CHUNK_DELAY)
    chunks = (total + chunk_size - 1) // chunk_size
    print(f"  Sent {label}: {total:,} bytes ({chunks} chunks, {chunk_size}B each)")


async def ble_command(client, cmd_bytes, label="cmd", wait=0.3):
    """Send a short command."""
    await client.write_gatt_char(WRITE_CHAR_UUID, cmd_bytes, response=False)
    await asyncio.sleep(wait)


async def find_printer(address=None, timeout=8.0):
    """Scan for printer or connect to specific address."""
    if address:
        print(f"  Using address: {address}")
        return address

    print("  Scanning for printers...")
    # return_adv=True gives us (BLEDevice, AdvertisementData) pairs. RSSI
    # lives on AdvertisementData as of Bleak 0.19+; BLEDevice.rssi was
    # removed in Bleak 1.0.
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    devices = [(d, adv) for d, adv in found.values()]

    for d, adv in devices:
        name = (d.name or "").upper()
        if any(kw in name for kw in SCAN_KEYWORDS):
            print(f"  Found: {d.name} ({d.address})")
            return d.address

    print("  Printer not found. Nearby BLE devices:")
    for d, adv in sorted(devices, key=lambda x: x[1].rssi or -999, reverse=True):
        if d.name:
            print(f"    {d.name:30s}  {d.address}  RSSI={adv.rssi}")
    print("\n  If your printer is listed above under a different name, use")
    print("  --address XX:XX:XX:XX:XX:XX to connect directly, skipping name matching.")
    return None


# ── Commands ──────────────────────────────────────────────────────────

async def cmd_scan(args):
    """Scan for nearby BLE devices."""
    print("Scanning for BLE devices...\n")
    found = await BleakScanner.discover(timeout=10.0, return_adv=True)
    devices = [(d, adv) for d, adv in found.values()]

    printers = []
    others = []
    for d, adv in sorted(devices, key=lambda x: x[1].rssi or -999, reverse=True):
        if not d.name:
            continue
        name_upper = d.name.upper()
        is_printer = any(kw in name_upper for kw in SCAN_KEYWORDS)
        (printers if is_printer else others).append((d, adv))

    if printers:
        print("Printers found:")
        for d, adv in printers:
            print(f"  * {d.name:30s}  {d.address}  RSSI={adv.rssi}")
    else:
        print("No known printers found. If yours is listed below under a")
        print("different name, connect with --address XX:XX:XX:XX:XX:XX and")
        print("it'll be treated as a printer directly, skipping name matching.")

    if others:
        print(f"\nOther BLE devices ({len(others)}):")
        for d, adv in others[:15]:
            print(f"    {d.name:30s}  {d.address}  RSSI={adv.rssi}")


async def cmd_info(args):
    """Get printer information."""
    address = await find_printer(args.address)
    if not address:
        return

    async with BleakClient(address, timeout=15.0) as client:
        await client.start_notify(NOTIFY_CHAR_UUID, notification_handler)
        await asyncio.sleep(0.3)

        queries = [
            ("Model",    bytes([0x10, 0xFF, 0x20, 0xF0])),
            ("Version",  bytes([0x10, 0xFF, 0x20, 0xF1])),
            ("Serial",   bytes([0x10, 0xFF, 0x20, 0xF2])),
            ("Battery",  bytes([0x10, 0xFF, 0x50, 0xF1])),
            ("Density",  bytes([0x10, 0xFF, 0x11])),
            ("Status",   bytes([0x10, 0xFF, 0x40])),
        ]

        print("\nPrinter Information:")
        print("-" * 40)

        for label, cmd in queries:
            received_data.clear()
            await ble_command(client, cmd, wait=0.5)
            if received_data:
                raw = received_data[-1]
                try:
                    text = raw.decode('ascii', errors='ignore').strip('\x00')
                    if text and text.isprintable():
                        print(f"  {label:12s}: {text}")
                    elif label == "Battery" and len(raw) >= 2:
                        print(f"  {label:12s}: {raw[1]}%")
                    elif label == "Status" and len(raw) >= 1:
                        status = raw[0]
                        flags = []
                        if status & 0x01: flags.append("printing")
                        if status & 0x02: flags.append("cover open")
                        if status & 0x04: flags.append("no paper")
                        if status & 0x08: flags.append("low battery")
                        if status & 0x50: flags.append("overheating")
                        if status & 0x20: flags.append("charging")
                        print(f"  {label:12s}: {', '.join(flags) if flags else 'ready'}")
                    else:
                        print(f"  {label:12s}: {raw.hex()}")
                except:
                    print(f"  {label:12s}: {raw.hex()}")
            else:
                print(f"  {label:12s}: no response")

        await client.stop_notify(NOTIFY_CHAR_UUID)


async def cmd_print(args, img):
    """Core print function."""
    address = await find_printer(args.address)
    if not address:
        return

    width_px = args.width
    bitmap_data, width_bytes, height_px = image_to_bitmap(img, width_px)
    gs_command = build_gs_v_0(bitmap_data, width_bytes, height_px)

    print(f"  Image: {width_bytes * 8}x{height_px} px")
    print(f"  Data:  {len(gs_command):,} bytes")

    copies = getattr(args, 'copies', 1) or 1
    label_mode = getattr(args, 'label', False)

    async with BleakClient(address, timeout=15.0) as client:
        await client.start_notify(NOTIFY_CHAR_UUID, notification_handler)
        await asyncio.sleep(0.3)

        # Set density if specified
        if args.density is not None:
            density = max(0, min(2, args.density))
            print(f"  Setting density: {density}")
            await ble_command(client, bytes([0x10, 0xFF, 0x10, 0x00, density]))

        for copy in range(copies):
            if copies > 1:
                print(f"\n  Copy {copy + 1}/{copies}")

            # Enable printer
            await ble_command(client, bytes([0x10, 0xFF, 0xF1, 0x03]))

            # Wake up
            await ble_command(client, bytes(12))

            # Label mode: adjust position on first copy
            if label_mode and copy == 0:
                await ble_command(client, bytes([0x1F, 0x11, 0x51]))

            # Send bitmap
            print("  Printing...")
            await ble_send_chunked(client, gs_command, "bitmap")
            await asyncio.sleep(0.5)

            if label_mode:
                # Position to next label
                await ble_command(client, bytes([0x1D, 0x0C]))
                # Adjust position on last copy
                if copy == copies - 1:
                    await ble_command(client, bytes([0x1F, 0x11, 0x50]))
            else:
                # Feed paper
                feed = args.feed or DEFAULT_FEED
                await ble_command(client, bytes([0x1B, 0x4A, feed]))

            # Stop print job
            await ble_command(client, bytes([0x10, 0xFF, 0xF1, 0x45]), wait=2.0)

        await client.stop_notify(NOTIFY_CHAR_UUID)

    print("  Done!")


async def cmd_test(args):
    """Print a test pattern."""
    print("Printing test pattern...")
    img = create_test_image(args.width)
    if args.dither:
        img = floyd_steinberg_dither(img)
    await cmd_print(args, img)


async def cmd_image(args):
    """Print an image file."""
    print(f"Printing: {args.file}")
    img = prepare_image(args.file, args.width, args.dither, args.invert)
    await cmd_print(args, img)


async def cmd_text(args):
    """Print text."""
    print(f"Printing text: {args.text!r}")
    font_size = getattr(args, 'font_size', 48) or 48
    img = create_text_image(args.text, args.width, font_size)
    await cmd_print(args, img)


# ── CLI ───────────────────────────────────────────────────────────────

def _add_shared_options(p, suppress_defaults=False):
    """Add the options shared by every command (--address, --width, etc).

    These are registered on both the top-level parser and every subparser,
    so they work whether given before or after the command name, e.g. both
    `print.py --address AA:BB:.. info` and `print.py info --address AA:BB:..`.

    When registered on a subparser, defaults are suppressed (not set at
    all) so that omitting the flag there doesn't stomp on a value already
    supplied before the command name. See argparse.SUPPRESS docs: a
    suppressed default means the attribute is only set if the user actually
    passes the flag.
    """
    d = argparse.SUPPRESS if suppress_defaults else None
    default_width = argparse.SUPPRESS if suppress_defaults else DEFAULT_WIDTH
    default_feed = argparse.SUPPRESS if suppress_defaults else DEFAULT_FEED
    default_copies = argparse.SUPPRESS if suppress_defaults else 1

    p.add_argument('--address', '-a', default=d, help='Printer BLE address (skip scanning)')
    p.add_argument('--width', '-w', type=int, default=default_width,
                    help=f'Print width in pixels (default: {DEFAULT_WIDTH})')
    p.add_argument('--density', '-d', type=int, choices=[0, 1, 2],
                    default=d, help='Print density (0=light, 1=normal, 2=dark)')
    p.add_argument('--feed', '-f', type=int, default=default_feed,
                    help=f'Paper feed after print in dots (default: {DEFAULT_FEED})')
    p.add_argument('--dither', action='store_true', default=d,
                    help='Use Floyd-Steinberg dithering')
    p.add_argument('--invert', action='store_true', default=d,
                    help='Invert colours')
    p.add_argument('--label', action='store_true', default=d,
                    help='Label/sticker mode (gap detection)')
    p.add_argument('--copies', '-c', type=int, default=default_copies,
                    help='Number of copies (default: 1)')


def main():
    parser = argparse.ArgumentParser(
        description="Print to Crafts & Co 3128 thermal printer via BLE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    _add_shared_options(parser)

    subparsers = parser.add_subparsers(dest='command', help='Command')

    for name, help_text in [('scan', 'Scan for BLE printers'),
                             ('info', 'Show printer info'),
                             ('test', 'Print test pattern')]:
        _add_shared_options(subparsers.add_parser(name, help=help_text), suppress_defaults=True)

    img_parser = subparsers.add_parser('image', help='Print an image')
    img_parser.add_argument('file', help='Image file to print (PNG, JPG, etc.)')
    _add_shared_options(img_parser, suppress_defaults=True)

    txt_parser = subparsers.add_parser('text', help='Print text')
    txt_parser.add_argument('text', help='Text to print')
    txt_parser.add_argument('--font-size', type=int, default=48,
                            help='Font size in pixels (default: 48)')
    _add_shared_options(txt_parser, suppress_defaults=True)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        'scan': cmd_scan,
        'info': cmd_info,
        'test': cmd_test,
        'image': cmd_image,
        'text': cmd_text,
    }

    asyncio.run(commands[args.command](args))


if __name__ == '__main__':
    main()
