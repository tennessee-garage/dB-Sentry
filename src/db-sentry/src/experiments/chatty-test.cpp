#include <Arduino.h>
#include "driver/i2s.h"
#include <math.h>

// ========================
// Pin + audio configuration
// ========================

// I2S port
#define I2S_PORT I2S_NUM_0

// Adjust these pin numbers to match your Xiao ESP32-C3 wiring
// These are just example choices:
const int I2S_WS_PIN  = D2;   // LRCLK / WS
const int I2S_SCK_PIN = D1;   // BCLK / SCK
const int I2S_SD_PIN  = D0;   // SD (data from mic)

// Audio parameters
const uint32_t SAMPLE_RATE        = 16000;   // 16 kHz is plenty for level metering
const size_t   SAMPLE_COUNT       = 1024;    // ~64 ms window at 16 kHz
const uint32_t REPORT_INTERVAL_MS = 1000;    // print once per second

uint32_t lastReportMs = 0;


// ========================
// I2S setup
// ========================
void setupI2S() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = SAMPLE_RATE;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;      // read as 32-bit words
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;      // stereo frame: {R, L, R, L, ...}
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 4;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;
  cfg.tx_desc_auto_clear = false;
  cfg.fixed_mclk = 0;

  i2s_pin_config_t pin_cfg = {};
  pin_cfg.bck_io_num   = I2S_SCK_PIN;
  pin_cfg.ws_io_num    = I2S_WS_PIN;
  pin_cfg.data_out_num = I2S_PIN_NO_CHANGE;  // RX only
  pin_cfg.data_in_num  = I2S_SD_PIN;

  // Install and start I2S driver
  i2s_driver_install(I2S_PORT, &cfg, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_cfg);

  // Stereo clock; the ICS-43432 drives one channel (RIGHT, because LR is high)
  i2s_set_clk(I2S_PORT, SAMPLE_RATE, I2S_BITS_PER_SAMPLE_32BIT, I2S_CHANNEL_STEREO);
}

void dumpSomeSamples() {
	const size_t TEST_SAMPLES = 64;   // small chunk to print
	int32_t buf[TEST_SAMPLES];
	size_t bytesRead = 0;

	i2s_zero_dma_buffer(I2S_PORT);

	esp_err_t res = i2s_read(
		I2S_PORT,
		(void *)buf,
		sizeof(buf),
		&bytesRead,
		200 / portTICK_PERIOD_MS   // 200ms timeout
	);

	Serial.print("i2s_read res="); Serial.print((int)res);
	Serial.print(" bytesRead="); Serial.println(bytesRead);

	if (res != ESP_OK || bytesRead == 0) {
		Serial.println("No data.");
		return;
	}

	size_t n = bytesRead / sizeof(int32_t);
	Serial.print("sample count="); Serial.println(n);

	// Print first 16 raw 32-bit words
	Serial.println("First 16 raw samples (hex):");
	for (size_t i = 0; i < n && i < 16; ++i) {
		Serial.printf("%08X ", buf[i]);
	}
	Serial.println();

	// Now compute a simple RMS over *all* words, ignoring channels for the moment
	double sumSq = 0.0;
	for (size_t i = 0; i < n; ++i) {
		int32_t s = buf[i] >> 8;  // top 24 bits
		sumSq += (double)s * (double)s;
	}
	double rms = sqrt(sumSq / (double)n);
	Serial.print("RMS(all words)="); Serial.println(rms);

	double sumSqRight = 0.0;
	double sumSqLeft  = 0.0;
	size_t countRight = 0;
	size_t countLeft  = 0;

	for (size_t i = 0; i + 1 < n; i += 2) {
	int32_t r = buf[i]   >> 8; // RIGHT
	int32_t l = buf[i+1] >> 8; // LEFT
	sumSqRight += (double)r * (double)r;
	sumSqLeft  += (double)l * (double)l;
	countRight++;
	countLeft++;
	}

	double rmsR = countRight ? sqrt(sumSqRight / (double)countRight) : 0.0;
	double rmsL = countLeft  ? sqrt(sumSqLeft  / (double)countLeft)  : 0.0;

	Serial.print("RMS Right="); Serial.println(rmsR);
	Serial.print("RMS Left ="); Serial.println(rmsL);
}

// ========================
// Arduino setup + loop
// ========================
void setup() {
	Serial.begin(115200);
	while (!Serial) {
		; // wait for USB (optional)
	}

	Serial.println();
	Serial.println("ICS-43432 I2S mic level test (Xiao ESP32-C3, LR=HIGH => RIGHT channel)");
	Serial.println("Initializing I2S...");

	setupI2S();
	
	delay(200); // let things settle
	
	Serial.println("I2S pin map check:");
  	Serial.printf("  BCLK: %d\n  WS: %d\n  SD: %d\n", I2S_SCK_PIN, I2S_WS_PIN, I2S_SD_PIN);

	Serial.println("Dumping some samples...");
	dumpSomeSamples();
	Serial.println("Done dumping.");
}

void loop() {
  // nothing for the moment
}