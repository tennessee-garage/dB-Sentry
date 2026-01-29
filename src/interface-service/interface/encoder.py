"""Rotary encoder control for Raspberry Pi.

Converted from C++ EncoderControl class. Provides polling-based rotary encoder
reading with button press detection and debouncing.
"""
import time
import logging

from typing import Optional, Callable
from config.app_config import cfg
from gpiozero import RotaryEncoder, Button

logger = logging.getLogger(__name__)


class EncoderControl:
    """Controls a rotary encoder with integrated button.
    
    Attributes:
        BUTTON_DEBOUNCE_MS: Debounce time in milliseconds for button presses
    """
    
    BUTTON_DEBOUNCE_MS = 50  # milliseconds
    
    def __init__(self, data_pin: int = 0, clock_pin: int = 0, button_pin: int = 0, max_value: int = 255):
        """Initialize the encoder control.
        
        Args:
            data_pin: GPIO pin number for encoder data (DT)
            clock_pin: GPIO pin number for encoder clock (CLK)
            button_pin: GPIO pin number for encoder button (SW)
            max_value: Maximum value the encoder can reach (default 255)
        """
        self._data_pin = data_pin if data_pin != 0 else cfg.encoder_data_pin
        self._clock_pin = clock_pin if clock_pin != 0 else cfg.encoder_clock_pin
        self._button_pin = button_pin if button_pin != 0 else cfg.encoder_button_pin
        
        self.encoder = RotaryEncoder(a=self._data_pin, b=self._clock_pin, max_steps=max_value, wrap=False)
        self.button = Button(self._button_pin, pull_up=True, bounce_time=0.05)

    def register_rotate_callback(self, callback: Callable[[int, int], None]) -> None:
        """Register a callback for rotation events.

        Args:
            callback: Function to call on rotation (receives steps delta and current steps)
        """
        last_steps = self.current_value()

        def on_rotated():
            nonlocal last_steps
            steps = self.encoder.steps
            delta = steps - last_steps
            last_steps = steps
            callback(delta, steps)

        self.encoder.when_rotated = on_rotated

    def register_button_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback for button press events.

        Args:
            callback: Function to call on button press
        """
        self.button.when_pressed = callback
    
    def current_value(self) -> int:
        """Get the current encoder value.
        
        Returns:
            Current value (0 to max_value)
        """
        return self.encoder.steps
    
    def clear_value(self):
        """Reset the encoder value to 0."""
        self.encoder.steps = 0
