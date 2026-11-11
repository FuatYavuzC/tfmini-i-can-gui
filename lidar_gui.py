"""TFmini-i-CAN için gerçek zamanlı mesafe grafik arayüzü."""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from math import ceil
from tkinter import ttk

import can
from serial.tools import list_ports

from raw_lidar import SUPPORTED_BITRATES, decode_measurement


GRAPH_SECONDS = 10.0
GRAPH_REFRESH_MS = 50


@dataclass(frozen=True)
class Measurement:
    received_at: float
    distance_cm: int
    strength: int
    sensor_timestamp_ms: int


class LidarApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TFmini-i CAN Mesafe İzleyici")
        self.root.geometry("1000x680")
        self.root.minsize(780, 520)

        self.events: queue.Queue[tuple[str, object | None]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.history: deque[tuple[float, float]] = deque(maxlen=5000)
        self.frame_count = 0
        self.last_rate_time = time.monotonic()
        self.last_rate_count = 0

        self.channel_var = tk.StringVar(value="COM4")
        self.bitrate_var = tk.StringVar(value="250000")
        self.can_id_var = tk.StringVar(value="0x003")
        self.status_var = tk.StringVar(value="Bağlantı bekleniyor")
        self.distance_var = tk.StringVar(value="--.-- m")
        self.distance_cm_var = tk.StringVar(value="--- cm")
        self.strength_var = tk.StringVar(value="---")
        self.timestamp_var = tk.StringVar(value="--- ms")
        self.rate_var = tk.StringVar(value="0.0 Hz")

        self._configure_style()
        self._build_ui()
        self._refresh_ports()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(20, self._process_events)
        self.root.after(GRAPH_REFRESH_MS, self._draw_graph)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background="#f2f5f7")
        style.configure(
            "Title.TLabel",
            background="#f2f5f7",
            foreground="#15242e",
            font=("Segoe UI", 20, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background="#f2f5f7",
            foreground="#60717d",
            font=("Segoe UI", 10),
        )
        style.configure("Card.TFrame", background="white", relief="solid", borderwidth=1)
        style.configure(
            "CardTitle.TLabel",
            background="white",
            foreground="#647681",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Distance.TLabel",
            background="white",
            foreground="#087f5b",
            font=("Segoe UI", 36, "bold"),
        )
        style.configure(
            "CardValue.TLabel",
            background="white",
            foreground="#1b2b34",
            font=("Segoe UI", 17, "bold"),
        )
        style.configure("Status.TLabel", background="#f2f5f7", font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(18, 8))

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, style="App.TFrame", padding=18)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)

        ttk.Label(main, text="TFmini-i CAN Mesafe İzleyici", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            main,
            text="USB-CAN Analyzer · 250 kbit/s · Standart CAN · ID 0x003",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 14))

        controls = ttk.LabelFrame(main, text="Bağlantı", padding=10)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        controls.columnconfigure(7, weight=1)

        ttk.Label(controls, text="Kanal").grid(row=0, column=0, padx=(0, 5))
        self.channel_box = ttk.Combobox(
            controls, textvariable=self.channel_var, width=10, state="normal"
        )
        self.channel_box.grid(row=0, column=1, padx=(0, 5))
        self.refresh_button = ttk.Button(controls, text="↻", width=3, command=self._refresh_ports)
        self.refresh_button.grid(row=0, column=2, padx=(0, 14))

        ttk.Label(controls, text="CAN hızı").grid(row=0, column=3, padx=(0, 5))
        self.bitrate_box = ttk.Combobox(
            controls,
            textvariable=self.bitrate_var,
            values=[str(value) for value in SUPPORTED_BITRATES],
            width=10,
            state="readonly",
        )
        self.bitrate_box.grid(row=0, column=4, padx=(0, 14))

        ttk.Label(controls, text="CAN ID").grid(row=0, column=5, padx=(0, 5))
        self.can_id_entry = ttk.Entry(controls, textvariable=self.can_id_var, width=10)
        self.can_id_entry.grid(row=0, column=6, padx=(0, 14))

        self.start_button = ttk.Button(
            controls, text="Başlat", style="Accent.TButton", command=self._toggle_connection
        )
        self.start_button.grid(row=0, column=8, sticky="e")

        cards = ttk.Frame(main, style="App.TFrame")
        cards.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        for column in range(4):
            cards.columnconfigure(column, weight=1, uniform="card")

        distance_card = ttk.Frame(cards, style="Card.TFrame", padding=13)
        distance_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(distance_card, text="MESAFE", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(distance_card, textvariable=self.distance_var, style="Distance.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            distance_card, textvariable=self.distance_cm_var, style="CardTitle.TLabel"
        ).pack(anchor="w")

        self._make_card(cards, 1, "SİNYAL GÜCÜ", self.strength_var)
        self._make_card(cards, 2, "SENSÖR ZAMANI", self.timestamp_var)
        self._make_card(cards, 3, "ÖLÇÜM HIZI", self.rate_var, right_padding=True)

        graph_frame = ttk.LabelFrame(main, text=f"Son {GRAPH_SECONDS:.0f} saniye", padding=6)
        graph_frame.grid(row=4, column=0, sticky="nsew")
        graph_frame.rowconfigure(0, weight=1)
        graph_frame.columnconfigure(0, weight=1)

        self.graph = tk.Canvas(
            graph_frame,
            background="#10242d",
            highlightthickness=0,
            bd=0,
        )
        self.graph.grid(row=0, column=0, sticky="nsew")

        status_bar = ttk.Frame(main, style="App.TFrame")
        status_bar.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        status_bar.columnconfigure(1, weight=1)
        self.status_dot = tk.Canvas(
            status_bar,
            width=14,
            height=14,
            background="#f2f5f7",
            highlightthickness=0,
        )
        self.status_dot.grid(row=0, column=0, padx=(0, 5))
        self._set_status("Bağlantı bekleniyor", "#8998a2")
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Button(status_bar, text="Grafiği temizle", command=self._clear_graph).grid(
            row=0, column=2, sticky="e"
        )

    def _make_card(
        self,
        parent: ttk.Frame,
        column: int,
        title: str,
        value: tk.StringVar,
        right_padding: bool = False,
    ) -> None:
        padding = (6, 0) if right_padding else (6, 6)
        card = ttk.Frame(parent, style="Card.TFrame", padding=13)
        card.grid(row=0, column=column, sticky="nsew", padx=padding)
        ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(card, textvariable=value, style="CardValue.TLabel").pack(
            anchor="w", pady=(10, 0)
        )

    def _refresh_ports(self) -> None:
        ports = [port.device for port in list_ports.comports()]
        self.channel_box["values"] = ports
        if "COM4" in ports:
            self.channel_var.set("COM4")
        elif ports and self.channel_var.get() not in ports:
            self.channel_var.set(ports[0])

    def _toggle_connection(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.stop_event.set()
            self.start_button.configure(state="disabled")
            self._set_status("Bağlantı durduruluyor...", "#e0a800")
            return

        channel = self.channel_var.get().strip()
        if not channel:
            self._set_status("Bir CAN adaptör kanalı seçin.", "#d33f49")
            return

        try:
            bitrate = int(self.bitrate_var.get())
            can_id = int(self.can_id_var.get(), 0)
            if not 0 < can_id <= 0x7FF:
                raise ValueError
        except ValueError:
            self._set_status("Standart CAN ID, 0x001–0x7FF arasında olmalı.", "#d33f49")
            return

        self.stop_event.clear()
        self._set_controls_enabled(False)
        self.start_button.configure(text="Durdur", state="normal")
        self._set_status("USB-CAN Analyzer açılıyor...", "#e0a800")
        self.worker = threading.Thread(
            target=self._can_worker,
            args=(channel, bitrate, can_id),
            daemon=True,
        )
        self.worker.start()

    def _can_worker(self, channel: str, bitrate: int, can_id: int) -> None:
        bus: can.BusABC | None = None
        error: str | None = None
        try:
            bus = can.Bus(
                interface="seeedstudio",
                channel=channel,
                bitrate=bitrate,
                frame_type="STD",
                operation_mode="normal",
                can_filters=[{"can_id": can_id, "can_mask": 0x7FF, "extended": False}],
            )
            self.events.put(("connected", f"{channel} · {bitrate} bit/s · ID 0x{can_id:03X}"))

            while not self.stop_event.is_set():
                message = bus.recv(timeout=0.2)
                if message is None or message.arbitration_id != can_id:
                    continue
                try:
                    distance_cm, strength, sensor_timestamp_ms = decode_measurement(message)
                except ValueError:
                    continue
                self.events.put(
                    (
                        "measurement",
                        Measurement(
                            received_at=time.monotonic(),
                            distance_cm=distance_cm,
                            strength=strength,
                            sensor_timestamp_ms=sensor_timestamp_ms,
                        ),
                    )
                )
        except PermissionError:
            error = (
                f"{channel} başka bir program tarafından kullanılıyor. "
                "USB-CAN Analyzer yazılımını kapatın."
            )
        except (can.CanError, OSError, ValueError) as exc:
            error = f"CAN bağlantısı kurulamadı: {exc}"
        finally:
            if bus is not None:
                bus.shutdown()
            self.events.put(("disconnected", error))

    def _process_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "connected":
                    self._set_status(f"Bağlı · {payload}", "#19a974")
                elif event == "measurement" and isinstance(payload, Measurement):
                    self._update_measurement(payload)
                elif event == "disconnected":
                    self.worker = None
                    self._set_controls_enabled(True)
                    self.start_button.configure(text="Başlat", state="normal")
                    if payload:
                        self._set_status(str(payload), "#d33f49")
                    else:
                        self._set_status("Bağlantı durduruldu", "#8998a2")
        except queue.Empty:
            pass

        self.root.after(20, self._process_events)

    def _update_measurement(self, measurement: Measurement) -> None:
        self.frame_count += 1
        self.strength_var.set(str(measurement.strength))
        self.timestamp_var.set(f"{measurement.sensor_timestamp_ms} ms")

        if measurement.distance_cm == 0xFFFF:
            self.distance_var.set("Geçersiz")
            self.distance_cm_var.set("Sinyal eşiğinin altında")
        else:
            distance_m = measurement.distance_cm / 100.0
            self.distance_var.set(f"{distance_m:.2f} m")
            self.distance_cm_var.set(f"{measurement.distance_cm} cm")
            self.history.append((measurement.received_at, distance_m))

        now = time.monotonic()
        elapsed = now - self.last_rate_time
        if elapsed >= 1.0:
            rate = (self.frame_count - self.last_rate_count) / elapsed
            self.rate_var.set(f"{rate:.1f} Hz")
            self.last_rate_time = now
            self.last_rate_count = self.frame_count

    def _draw_graph(self) -> None:
        canvas = self.graph
        canvas.delete("all")
        width = max(canvas.winfo_width(), 100)
        height = max(canvas.winfo_height(), 100)
        left, right, top, bottom = 62, 18, 18, 42
        plot_width = max(width - left - right, 1)
        plot_height = max(height - top - bottom, 1)
        now = time.monotonic()
        cutoff = now - GRAPH_SECONDS

        while self.history and self.history[0][0] < cutoff - 1:
            self.history.popleft()
        points = [(stamp, value) for stamp, value in self.history if stamp >= cutoff]

        max_value = max((value for _, value in points), default=1.0)
        y_max = max(1.0, ceil(max_value * 2.2) / 2.0)

        for index in range(6):
            fraction = index / 5
            y = top + plot_height * fraction
            value = y_max * (1 - fraction)
            canvas.create_line(left, y, width - right, y, fill="#29434e", width=1)
            canvas.create_text(
                left - 8,
                y,
                text=f"{value:.1f}",
                fill="#9bb0ba",
                anchor="e",
                font=("Segoe UI", 9),
            )

        for index in range(6):
            fraction = index / 5
            x = left + plot_width * fraction
            seconds = -GRAPH_SECONDS * (1 - fraction)
            canvas.create_line(x, top, x, height - bottom, fill="#203943", width=1)
            canvas.create_text(
                x,
                height - bottom + 18,
                text=f"{seconds:.0f}s",
                fill="#9bb0ba",
                anchor="n",
                font=("Segoe UI", 9),
            )

        canvas.create_text(
            8,
            8,
            text="Mesafe (m)",
            fill="#b7c7ce",
            anchor="nw",
            font=("Segoe UI", 9, "bold"),
        )

        if len(points) >= 2:
            coordinates: list[float] = []
            for stamp, value in points:
                x = left + ((stamp - cutoff) / GRAPH_SECONDS) * plot_width
                y = top + (1 - min(value / y_max, 1.0)) * plot_height
                coordinates.extend((x, y))
            canvas.create_line(
                *coordinates,
                fill="#37d6a0",
                width=2,
                smooth=False,
            )
            x, y = coordinates[-2], coordinates[-1]
            canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#ffffff", outline="#37d6a0")
        elif not points:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Ölçüm bekleniyor...",
                fill="#78909b",
                font=("Segoe UI", 15),
            )

        self.root.after(GRAPH_REFRESH_MS, self._draw_graph)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.channel_box.configure(state="normal" if enabled else "disabled")
        self.refresh_button.configure(state="normal" if enabled else "disabled")
        self.bitrate_box.configure(state="readonly" if enabled else "disabled")
        self.can_id_entry.configure(state="normal" if enabled else "disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status_var.set(text)
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 12, 12, fill=color, outline=color)

    def _clear_graph(self) -> None:
        self.history.clear()

    def _on_close(self) -> None:
        self.stop_event.set()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    LidarApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
