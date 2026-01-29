from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
	led_simulate: bool = os.getenv("LED_SIMULATE", "false").lower() in ("1", "true", "yes")
	led_count: int = int(os.getenv("LED_COUNT", "20"))
	led_pin: int = int(os.getenv("LED_PIN", "18"))

	# Note that these use BCM GPIO pin numbers e.g. GPIO19 will be 19 here.
	encoder_data_pin: int = int(os.getenv("ENCODER_DATA_PIN", "19"))
	encoder_clock_pin: int = int(os.getenv("ENCODER_CLOCK_PIN", "13"))
	encoder_button_pin: int = int(os.getenv("ENCODER_BUTTON_PIN", "26"))

cfg = Config()
