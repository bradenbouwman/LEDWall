"""
LED Wall Controller
32 rows x 96 cols = 3072 LEDs
Split: LEFT = cols 0-47, RIGHT = cols 48-95
Each half → its own ESP32 via DDP
 
Leave ESP32_RIGHT = "" to run with just one ESP32 (sends full frame to LEFT).
"""
 
import socket
import struct
import threading
import numpy as np
from PIL import Image
 
# ── Config ──────────────────────────────────────────────────
ESP32_LEFT  = "192.168.1.17"  # cols 0–47
ESP32_RIGHT = "".strip()              # cols 48–95 — leave blank to use one ESP32 only
DDP_PORT    = 4048
 
ROWS        = 32
COLS        = 96
HALF_COLS   = COLS // 2       # 48
 
SERPENTINE  = Falsxqe           # Set True if strips alternate direction
 
# ── DDP Constants (from LedFx) ───────────────────────────────
VER1        = 0x40
PUSH        = 0x01
DATATYPE    = 0x0B            # RGB, 8-bit
DEST_ID     = 0x01
MAX_PIXELS  = 480
MAX_BYTES   = MAX_PIXELS * 3  # 1440 bytes per packet
 
frame_count = 0
 
 
# ── Serpentine remapping ─────────────────────────────────────
def remap_serpentine(pixels_2d: np.ndarray) -> np.ndarray:
    out = []
    for row in range(pixels_2d.shape[0]):
        if SERPENTINE and row % 2 == 1:
            out.append(pixels_2d[row, ::-1])
        else:
            out.append(pixels_2d[row, :])
    return np.vstack(out)
 
 
# ── DDP Packet Builder ───────────────────────────────────────
def send_ddp(sock: socket.socket, ip: str, pixels: np.ndarray, seq: int):
    byte_data = memoryview(pixels.astype(np.uint8).ravel())
    total = len(byte_data)
 
    packets, remainder = divmod(total, MAX_BYTES)
    if remainder == 0:
        packets -= 1
 
    for i in range(packets + 1):
        start   = i * MAX_BYTES
        chunk   = byte_data[start : start + MAX_BYTES]
        is_last = (i == packets)
 
        header = struct.pack(
            "!BBBBLH",
            VER1 | (PUSH if is_last else 0),
            seq,
            DATATYPE,
            DEST_ID,
            start,
            len(chunk),
        )
        sock.sendto(header + bytes(chunk), (ip, DDP_PORT))
 
 
# ── Frame Sender ─────────────────────────────────────────────
def send_frame(image_path: str):
    global frame_count
 
    img = Image.open(image_path).convert("RGB")
    img = img.resize((COLS, ROWS), Image.LANCZOS)
    pixels_2d = np.array(img)
 
    frame_count += 1
    seq = frame_count % 15 + 1
 
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
 
    print(f"LEFT: '{ESP32_LEFT}'")
    print(f"RIGHT: '{ESP32_RIGHT}'")

    if ESP32_RIGHT and ESP32_RIGHT.strip():        # Two ESP32s — split the frame in half
        pixels_left  = remap_serpentine(pixels_2d[:, :HALF_COLS])
        pixels_right = remap_serpentine(pixels_2d[:, HALF_COLS:])
        t1 = threading.Thread(target=send_ddp, args=(sock, ESP32_LEFT,  pixels_left,  seq))
        t2 = threading.Thread(target=send_ddp, args=(sock, ESP32_RIGHT, pixels_right, seq))
        t1.start(); t2.start()
        t1.join();  t2.join()
        print(f"Frame {frame_count} sent to both ESP32s (seq={seq})")
    else:
        # One ESP32 — send full frame
        pixels = remap_serpentine(pixels_2d)
        send_ddp(sock, ESP32_LEFT, pixels, seq)
        print(f"Frame {frame_count} sent to {ESP32_LEFT} (seq={seq})")
 
    sock.close()
 
 
# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    image_path = sys.argv[1] if len(sys.argv) > 1 else "frame.png"
    send_frame(image_path)