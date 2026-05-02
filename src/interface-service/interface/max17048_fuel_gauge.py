"""MAX17048 fuel gauge interface for Raspberry Pi I2C.

This module provides a small, reusable interface class for reading battery
metrics from a MAX17048 (or MAX17049-compatible) fuel gauge.
"""

from __future__ import annotations

from collections import deque
import logging
import time
from typing import Any, Deque, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from smbus2 import SMBus

    _HAVE_SMBUS2 = True
except Exception:
    SMBus = None  # type: ignore
    _HAVE_SMBUS2 = False

try:
    from gpiozero import Button

    _HAVE_GPIOZERO = True
except Exception:
    Button = None  # type: ignore
    _HAVE_GPIOZERO = False


class MAX17048FuelGauge:
    """Read metrics from a MAX17048 fuel gauge over I2C.

    Notes:
    - MAX17048 default I2C address is 0x36.
    - Raspberry Pi usually exposes I2C bus 1 on GPIO2 (SDA) and GPIO3 (SCL).
    - The ~ALERT line is active-low; if configured, alert is read on GPIO.
    """

    DEFAULT_I2C_ADDRESS = 0x36

    REG_VCELL = 0x02
    REG_SOC = 0x04
    REG_VERSION = 0x08
    REG_CRATE = 0x16
    REG_STATUS = 0x1A

    def __init__(
        self,
        bus_number: int = 1,
        address: int = DEFAULT_I2C_ADDRESS,
        alert_pin: Optional[int] = 4,
        use_alert_gpio: bool = True,
        discharge_rate_window_size: int = 30,
        charge_trend_window_size: int = 128,
    ) -> None:
        self.bus_number = bus_number
        self.address = address
        self.alert_pin = alert_pin
        self.use_alert_gpio = use_alert_gpio
        self.discharge_rate_window_size = max(1, int(discharge_rate_window_size))
        self.charge_trend_window_size = max(1, int(charge_trend_window_size))

        self.bus: Optional[Any] = None
        self.alert_button: Optional[Any] = None
        self._init_error: Optional[str] = None
        self._crate_history: Deque[float] = deque(maxlen=self.discharge_rate_window_size)
        self._charge_per_minute_history: Deque[float] = deque(maxlen=self.charge_trend_window_size)
        self._soc_history: Deque[float] = deque(maxlen=self.charge_trend_window_size)
        self._last_soc_sample: Optional[float] = None
        self._last_soc_sample_time: Optional[float] = None

        self._initialize_bus()
        self._initialize_alert_input()

    def _initialize_bus(self) -> None:
        if not _HAVE_SMBUS2 or SMBus is None:
            self._init_error = (
                "smbus2 is not available. Install requirements and run on a system "
                "with I2C enabled."
            )
            logger.warning(self._init_error)
            return

        try:
            self.bus = SMBus(self.bus_number)
        except Exception as exc:
            self._init_error = f"Failed to open I2C bus {self.bus_number}: {exc}"
            logger.error(self._init_error)

    def _initialize_alert_input(self) -> None:
        if not self.use_alert_gpio or self.alert_pin is None:
            return

        if not _HAVE_GPIOZERO or Button is None:
            logger.warning("gpiozero unavailable; ALERT GPIO monitoring disabled")
            return

        try:
            # ~ALERT is active-low and typically uses pull-up wiring.
            self.alert_button = Button(self.alert_pin, pull_up=True)
        except Exception as exc:
            logger.warning("Failed to initialize ALERT GPIO pin %s: %s", self.alert_pin, exc)

    @property
    def is_ready(self) -> bool:
        """Return True when I2C communication is ready."""
        return self.bus is not None

    def _require_bus(self) -> Any:
        if self.bus is None:
            raise RuntimeError(self._init_error or "I2C bus is not initialized")
        return self.bus

    @staticmethod
    def _to_signed_16(value: int) -> int:
        return value - 0x10000 if (value & 0x8000) else value

    def _read_word_be(self, register: int) -> int:
        """Read a 16-bit register and convert SMBus little-endian to big-endian."""
        bus = self._require_bus()
        raw = bus.read_word_data(self.address, register)
        return ((raw & 0x00FF) << 8) | ((raw & 0xFF00) >> 8)

    def read_cell_voltage_v(self) -> float:
        """Read cell voltage in volts.

        VCELL uses the full 16-bit register with 78.125uV per LSB.
        """
        raw = self._read_word_be(self.REG_VCELL)
        return raw * 78.125e-6

    def read_soc_percent(self) -> float:
        """Read state of charge percentage."""
        raw = self._read_word_be(self.REG_SOC)
        return raw / 256.0

    def read_crate_percent_per_hour(self, record_history: bool = True) -> float:
        """Read charge/discharge rate in percent per hour.

        CRate is a signed 16-bit value with 0.208 %/hr per LSB.
        Positive means charging, negative means discharging.
        """
        raw = self._read_word_be(self.REG_CRATE)
        signed = self._to_signed_16(raw)
        rate = signed * 0.208
        if record_history:
            self._crate_history.append(rate)
        return rate

    def get_smoothed_crate_percent_per_hour(self) -> Optional[float]:
        """Return rolling-average CRate from recent samples."""
        if not self._crate_history:
            return None
        return sum(self._crate_history) / len(self._crate_history)

    def _record_charge_percentage_per_minute_sample(
        self,
        soc_percent: float,
        sample_time: Optional[float] = None,
    ) -> Optional[float]:
        """Record one SOC sample and store derived rate in %/minute.

        Returns the latest computed rate when at least one previous sample exists,
        otherwise None for the first sample.
        """
        now = sample_time if sample_time is not None else time.time()

        if self._last_soc_sample is None or self._last_soc_sample_time is None:
            self._last_soc_sample = soc_percent
            self._last_soc_sample_time = now
            return None

        elapsed_seconds = now - self._last_soc_sample_time
        if elapsed_seconds <= 0:
            return None

        delta_soc = soc_percent - self._last_soc_sample
        rate_per_minute = delta_soc / (elapsed_seconds / 60.0)

        self._last_soc_sample = soc_percent
        self._last_soc_sample_time = now
        self._charge_per_minute_history.append(rate_per_minute)
        return rate_per_minute

    def get_charge_percentage_per_minute_samples(self) -> list[float]:
        """Return the rolling history of SOC change rate samples (%/minute)."""
        return list(self._charge_per_minute_history)

    def get_soc_percent_history_samples(self) -> list[float]:
        """Return the rolling history of SOC percentage samples (0-100)."""
        return list(self._soc_history)

    def get_latest_charge_percentage_per_minute(self) -> Optional[float]:
        """Return the most recent SOC change rate sample (%/minute)."""
        if not self._charge_per_minute_history:
            return None
        return self._charge_per_minute_history[-1]

    def get_normalized_charge_trend_y(
        self,
        graph_height: int,
        center_zero: bool = True,
        fixed_scale_abs: Optional[float] = None,
    ) -> list[int]:
        """Return full-width OLED y-coordinates for the charge trend.

        The returned list length is always `charge_trend_window_size`, matching
        OLED pixel width when configured that way. Values are y pixel positions
        in the range 0..graph_height-1.

        Args:
            graph_height: Graph height in pixels.
            center_zero: If True, 0 %/min is centered vertically and values are
                normalized symmetrically around zero.
            fixed_scale_abs: Optional fixed absolute scale for center-zero mode.
                For example, 0.5 means +/-0.5 %/min spans full graph height.

        Returns:
            List of normalized y coordinates for plotting.
        """
        if graph_height <= 0:
            raise ValueError("graph_height must be positive")

        width = self.charge_trend_window_size
        samples = list(self._charge_per_minute_history)

        # Left-pad so callers always receive a full-width series.
        if len(samples) < width:
            pad_value = 0.0 if center_zero else (samples[0] if samples else 0.0)
            samples = [pad_value] * (width - len(samples)) + samples

        y_max = graph_height - 1

        if center_zero:
            if fixed_scale_abs is not None and fixed_scale_abs > 0:
                max_abs = fixed_scale_abs
            else:
                max_abs = max((abs(v) for v in samples), default=0.0)
                if max_abs == 0:
                    max_abs = 1.0

            mid = y_max / 2.0
            amp = y_max / 2.0
            points = [int(round(mid - (value / max_abs) * amp)) for value in samples]
        else:
            low = min(samples) if samples else 0.0
            high = max(samples) if samples else 0.0
            span = high - low
            if span == 0:
                span = 1.0

            points = [
                int(round(y_max * (1.0 - ((value - low) / span))))
                for value in samples
            ]

        return [max(0, min(y_max, y)) for y in points]

    def get_charge_trend_plot_points(
        self,
        graph_x: int,
        graph_y: int,
        graph_width: int,
        graph_height: int,
        center_zero: bool = True,
        fixed_scale_abs: Optional[float] = None,
    ) -> Tuple[list[tuple[int, int]], Optional[int]]:
        """Return OLED-ready plot points and optional zero-axis y position.

        Args:
            graph_x: Left x origin of graph area.
            graph_y: Top y origin of graph area.
            graph_width: Graph width in pixels.
            graph_height: Graph height in pixels.
            center_zero: If True, include a centered zero-axis reference.
            fixed_scale_abs: Optional fixed absolute scale for center-zero mode.

        Returns:
            A tuple of (plot_points, zero_axis_y):
            - plot_points: list of (x, y) coordinates clipped to graph bounds.
            - zero_axis_y: y coordinate for 0 %/min line, or None when not used.
        """
        if graph_width <= 0:
            raise ValueError("graph_width must be positive")

        y_values = self.get_normalized_charge_trend_y(
            graph_height=graph_height,
            center_zero=center_zero,
            fixed_scale_abs=fixed_scale_abs,
        )

        if len(y_values) > graph_width:
            y_values = y_values[-graph_width:]
        elif len(y_values) < graph_width:
            pad_y = int(round((graph_height - 1) / 2.0)) if center_zero else (y_values[0] if y_values else 0)
            y_values = [pad_y] * (graph_width - len(y_values)) + y_values

        points = [(graph_x + idx, graph_y + y) for idx, y in enumerate(y_values)]

        zero_axis_y: Optional[int]
        if center_zero:
            zero_axis_y = graph_y + int(round((graph_height - 1) / 2.0))
        else:
            zero_axis_y = None

        return points, zero_axis_y

    def get_normalized_soc_history_y(
        self,
        graph_height: int,
        min_percent: float = 0.0,
        max_percent: float = 100.0,
    ) -> list[int]:
        """Return full-width OLED y-coordinates for SOC history on fixed scale.

        The returned list length is always `charge_trend_window_size`.
        """
        if graph_height <= 0:
            raise ValueError("graph_height must be positive")
        if max_percent <= min_percent:
            raise ValueError("max_percent must be greater than min_percent")

        width = self.charge_trend_window_size
        samples = list(self._soc_history)

        if len(samples) < width:
            pad_value = min_percent
            samples = [pad_value] * (width - len(samples)) + samples

        y_max = graph_height - 1
        span = max_percent - min_percent

        points = [
            int(round(y_max * (1.0 - ((max(min_percent, min(max_percent, value)) - min_percent) / span))))
            for value in samples
        ]
        return [max(0, min(y_max, y)) for y in points]

    def get_soc_history_plot_points(
        self,
        graph_x: int,
        graph_y: int,
        graph_width: int,
        graph_height: int,
        min_percent: float = 0.0,
        max_percent: float = 100.0,
    ) -> list[tuple[int, int]]:
        """Return OLED-ready plot points for SOC history on fixed 0-100 style axis."""
        if graph_width <= 0:
            raise ValueError("graph_width must be positive")

        y_values = self.get_normalized_soc_history_y(
            graph_height=graph_height,
            min_percent=min_percent,
            max_percent=max_percent,
        )

        if len(y_values) > graph_width:
            y_values = y_values[-graph_width:]
        elif len(y_values) < graph_width:
            pad_y = graph_height - 1
            y_values = [pad_y] * (graph_width - len(y_values)) + y_values

        return [(graph_x + idx, graph_y + y) for idx, y in enumerate(y_values)]

    def clear_crate_history(self) -> None:
        """Clear accumulated CRate history used for smoothing."""
        self._crate_history.clear()

    def clear_charge_trend_history(self) -> None:
        """Clear SOC trend history and reset previous sample state."""
        self._charge_per_minute_history.clear()
        self._soc_history.clear()
        self._last_soc_sample = None
        self._last_soc_sample_time = None

    @staticmethod
    def estimate_time_remaining(
        soc_percent: float, crate_percent_per_hour: float
    ) -> Optional[tuple[int, int]]:
        """Estimate remaining runtime as hours and minutes.

        Args:
            soc_percent: Current state of charge in percent.
            crate_percent_per_hour: Current charge/discharge rate in percent/hour.

        Returns:
            A tuple of (hours, minutes) when the battery is discharging,
            or None when the estimate is not meaningful, such as when the
            battery is charging, the rate is zero, or the SOC is empty.
        """
        if soc_percent <= 0 or crate_percent_per_hour >= 0:
            return None

        discharge_rate = abs(crate_percent_per_hour)
        if discharge_rate == 0:
            return None

        remaining_hours = soc_percent / discharge_rate
        total_minutes = max(0, int(round(remaining_hours * 60)))
        return total_minutes // 60, total_minutes % 60

    def read_estimated_time_remaining(self, use_smoothed_rate: bool = True) -> Optional[tuple[int, int]]:
        """Read SOC and CRate, then estimate remaining runtime.

        Returns:
            A tuple of (hours, minutes), or None if no valid runtime estimate
            can be produced from the current readings.
        """
        soc_percent = self.read_soc_percent()
        crate_percent_per_hour = self.read_crate_percent_per_hour(record_history=True)
        if use_smoothed_rate:
            smoothed_rate = self.get_smoothed_crate_percent_per_hour()
            if smoothed_rate is not None:
                crate_percent_per_hour = smoothed_rate
        return self.estimate_time_remaining(soc_percent, crate_percent_per_hour)

    @staticmethod
    def format_time_remaining(
        time_remaining: Optional[tuple[int, int]],
        crate_percent_per_hour: Optional[float] = None,
    ) -> str:
        """Format a time-remaining tuple as XhYYm.

        Args:
            time_remaining: Tuple of (hours, minutes), or None.
            crate_percent_per_hour: Current charge/discharge rate in percent/hour.

        Returns:
            Formatted string such as 5h44m, "charging" when the current rate
            is positive, or n/a when unavailable.
        """
        if time_remaining is None:
            if crate_percent_per_hour is not None and crate_percent_per_hour > 0:
                return "charging"
            return "n/a"

        hours, minutes = time_remaining
        return f"{hours}h{minutes:02d}m"

    def read_estimated_time_remaining_text(self, use_smoothed_rate: bool = True) -> str:
        """Read and format estimated remaining runtime as text."""
        crate_percent_per_hour = self.read_crate_percent_per_hour(record_history=True)
        if use_smoothed_rate:
            smoothed_rate = self.get_smoothed_crate_percent_per_hour()
            if smoothed_rate is not None:
                crate_percent_per_hour = smoothed_rate

        return self.format_time_remaining(
            self.estimate_time_remaining(self.read_soc_percent(), crate_percent_per_hour),
            crate_percent_per_hour=crate_percent_per_hour,
        )

    def read_version(self) -> int:
        """Read IC version register."""
        return self._read_word_be(self.REG_VERSION)

    def read_status(self) -> int:
        """Read status register (raw 16-bit value)."""
        return self._read_word_be(self.REG_STATUS)

    def is_alert_asserted(self) -> Optional[bool]:
        """Return True if ~ALERT is active, False if inactive, None if unavailable."""
        if self.alert_button is None:
            return None
        return bool(self.alert_button.is_pressed)

    def read_metrics(self) -> Dict[str, Optional[float]]:
        """Read a standard metrics payload for consumers."""
        metrics: Dict[str, Optional[float]] = {
            "voltage_v": None,
            "soc_percent": None,
            "crate_percent_per_hour": None,
            "crate_smoothed_percent_per_hour": None,
            "charge_percent_per_minute": None,
            "status_raw": None,
            "version_raw": None,
            "alert_pin_asserted": None,
        }

        metrics["voltage_v"] = self.read_cell_voltage_v()
        metrics["soc_percent"] = self.read_soc_percent()
        self._soc_history.append(metrics["soc_percent"])
        metrics["charge_percent_per_minute"] = self._record_charge_percentage_per_minute_sample(
            metrics["soc_percent"]
        )
        metrics["crate_percent_per_hour"] = self.read_crate_percent_per_hour(record_history=True)
        metrics["crate_smoothed_percent_per_hour"] = self.get_smoothed_crate_percent_per_hour()
        metrics["status_raw"] = float(self.read_status())
        metrics["version_raw"] = float(self.read_version())

        alert_state = self.is_alert_asserted()
        metrics["alert_pin_asserted"] = None if alert_state is None else float(alert_state)

        return metrics

    def close(self) -> None:
        """Release I2C and GPIO resources."""
        if self.alert_button is not None:
            try:
                self.alert_button.close()
            except Exception:
                logger.exception("Failed to close ALERT GPIO input")
            finally:
                self.alert_button = None

        if self.bus is not None:
            try:
                self.bus.close()
            except Exception:
                logger.exception("Failed to close I2C bus")
            finally:
                self.bus = None

    def __enter__(self) -> "MAX17048FuelGauge":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
