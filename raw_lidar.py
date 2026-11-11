"""TFmini-i-CAN ölçümlerini USB-CAN Analyzer üzerinden okur."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

try:
    import can
except ImportError:
    print(
        "Hata: python-can kurulu değil. Kurmak için: "
        "python -m pip install \"python-can[seeedstudio]\"",
        file=sys.stderr,
    )
    raise SystemExit(1)


SUPPORTED_BITRATES = (
    100_000,
    125_000,
    200_000,
    250_000,
    400_000,
    500_000,
    800_000,
    1_000_000,
)


def can_id(value: str) -> int:
    """0x123 veya 123 biçimindeki CAN kimliğini sayıya çevirir."""
    try:
        result = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"geçersiz CAN ID: {value}") from exc

    if not 0 <= result <= 0x1FFFFFFF:
        raise argparse.ArgumentTypeError("CAN ID 0x0 ile 0x1FFFFFFF arasında olmalı")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "USB-CAN Analyzer üzerinden TFmini-i-CAN mesafe, sinyal gücü ve "
            "sensör zaman damgasını okur."
        )
    )
    parser.add_argument(
        "--channel",
        default="COM4",
        help="USB-CAN Analyzer'ın Windows kanalı (varsayılan: COM4)",
    )
    parser.add_argument(
        "--bitrate",
        type=int,
        choices=SUPPORTED_BITRATES,
        default=250_000,
        help="CAN veri yolu hızı, bit/s (TFmini-i varsayılanı: 250000)",
    )
    parser.add_argument(
        "--frame-type",
        choices=("STD", "EXT"),
        default="STD",
        help="11 bit standart veya 29 bit genişletilmiş CAN ID (varsayılan: STD)",
    )
    parser.add_argument(
        "--mode",
        choices=("normal", "silent"),
        default="normal",
        help="Adaptör çalışma modu (varsayılan: normal)",
    )
    parser.add_argument(
        "--id",
        dest="filter_id",
        type=can_id,
        default=0x003,
        help="TFmini-i gönderim CAN ID'si (varsayılan: 0x003)",
    )
    return parser.parse_args()


def make_filters(args: argparse.Namespace) -> list[dict[str, int | bool]]:
    is_extended = args.frame_type == "EXT"
    return [
        {
            "can_id": args.filter_id,
            "can_mask": 0x1FFFFFFF if is_extended else 0x7FF,
            "extended": is_extended,
        }
    ]


def decode_measurement(message: can.Message) -> tuple[int, int, int]:
    """TFmini-i'nin 8 baytlık CAN ölçümünü little-endian olarak çözer."""
    if message.is_remote_frame or message.is_error_frame:
        raise ValueError("ölçüm çerçevesi veri çerçevesi olmalı")
    if len(message.data) != 8:
        raise ValueError(f"TFmini-i ölçüm çerçevesi 8 bayt olmalı, gelen: {len(message.data)}")

    distance_cm = int.from_bytes(message.data[0:2], byteorder="little")
    strength = int.from_bytes(message.data[2:4], byteorder="little")
    sensor_timestamp_ms = int.from_bytes(message.data[4:8], byteorder="little")
    return distance_cm, strength, sensor_timestamp_ms


def format_message(message: can.Message) -> str:
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    id_width = 8 if message.is_extended_id else 3
    hex_data = " ".join(f"{byte:02X}" for byte in message.data)

    try:
        distance_cm, strength, sensor_timestamp_ms = decode_measurement(message)
    except ValueError as exc:
        return (
            f"[{timestamp}] ID=0x{message.arbitration_id:0{id_width}X} "
            f"ölçüm dışı çerçeve: {exc} | DATA: {hex_data or '-'}"
        )

    if distance_cm == 0xFFFF:
        distance_text = "GEÇERSİZ (0xFFFF)"
    else:
        distance_text = f"{distance_cm:5d} cm ({distance_cm / 100:6.2f} m)"

    return (
        f"[{timestamp}] ID=0x{message.arbitration_id:0{id_width}X} | "
        f"MESAFE: {distance_text} | GÜÇ: {strength:5d} | "
        f"SENSÖR_TS: {sensor_timestamp_ms:10d} ms | DATA: {hex_data}"
    )


def main() -> int:
    args = parse_args()

    try:
        bus = can.Bus(
            interface="seeedstudio",
            channel=args.channel,
            bitrate=args.bitrate,
            frame_type=args.frame_type,
            operation_mode=args.mode,
            can_filters=make_filters(args),
        )
    except PermissionError as exc:
        print(
            f"{args.channel} başka bir program tarafından kullanılıyor. "
            "USB-CAN Analyzer yazılımını/seri monitörü kapatıp tekrar deneyin. "
            f"Ayrıntı: {exc}",
            file=sys.stderr,
        )
        return 1
    except (can.CanError, OSError, ValueError) as exc:
        print(
            f"USB-CAN Analyzer açılamadı ({args.channel}, {args.bitrate} bit/s): {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        f"USB-CAN Analyzer açık: kanal={args.channel}, hız={args.bitrate} bit/s, "
        f"çerçeve={args.frame_type}, mod={args.mode}"
    )
    print(f"TFmini-i filtresi: CAN ID 0x{args.filter_id:X}")
    print("TFmini-i ölçümü bekleniyor... Çıkmak için Ctrl+C\n")

    try:
        while True:
            message = bus.recv(timeout=1.0)
            if message is not None:
                print(format_message(message))
    except KeyboardInterrupt:
        print("\nOkuma durduruldu.")
    except can.CanError as exc:
        print(f"CAN okuma hatası: {exc}", file=sys.stderr)
        return 1
    finally:
        bus.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
