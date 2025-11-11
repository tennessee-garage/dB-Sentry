#include <Arduino.h>
#include "driver/i2s.h"

#define I2S_PORT I2S_NUM_0

// Use D3 / D2 / D1 which map to GPIO5 / GPIO4 / GPIO3 on XIAO ESP32-C3
// (per Seeed's Arduino pinout doc)
const int I2S_WS_PIN  = D2;  // LRCLK / WS  (GPIO4)
const int I2S_SCK_PIN = D3;  // BCLK / SCK  (GPIO5)
const int I2S_SD_PIN  = D1;  // SD (data in) (GPIO3)

void setupI2S() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = 16000;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;      // stereo frame
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 4;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;
  cfg.tx_desc_auto_clear = false;
  cfg.fixed_mclk = 0;

  i2s_pin_config_t pins = {};
  pins.bck_io_num   = I2S_SCK_PIN;
  pins.ws_io_num    = I2S_WS_PIN;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num  = I2S_SD_PIN;

  Serial.println("Installing I2S driver...");
  esp_err_t err = i2s_driver_install(I2S_PORT, &cfg, 0, NULL);
  Serial.print("i2s_driver_install: "); Serial.println((int)err);
  if (err != ESP_OK) return;

  err = i2s_set_pin(I2S_PORT, &pins);
  Serial.print("i2s_set_pin: "); Serial.println((int)err);
  if (err != ESP_OK) return;

  err = i2s_set_clk(I2S_PORT, 16000, I2S_BITS_PER_SAMPLE_32BIT, I2S_CHANNEL_STEREO);
  Serial.print("i2s_set_clk: "); Serial.println((int)err);

  err = i2s_start(I2S_PORT);
  Serial.print("i2s_start: "); Serial.println((int)err);
}

void setup() {
	Serial.begin(115200);
	//while (!Serial) {}

	delay(400);

	Serial.println("\nXIAO ESP32-C3 I2S CLOCK TEST");
	Serial.printf("Using pins -> BCLK: %d  WS: %d  SD: %d\n",
					I2S_SCK_PIN, I2S_WS_PIN, I2S_SD_PIN);

	setupI2S();

	pinMode(D4, OUTPUT);
	digitalWrite(D4, HIGH);
}

void loop() {
	// Keep I2S RX busy so clocks keep running
	uint32_t dummy[64];
	size_t bytesRead = 0;
	esp_err_t err = i2s_read(I2S_PORT, dummy, sizeof(dummy), &bytesRead, 10);
	if (err != ESP_OK) {
		Serial.print("i2s_read err: "); Serial.println((int)err);
	}

	digitalWrite(D4, HIGH);
	delay(10);
	digitalWrite(D4, LOW);
}