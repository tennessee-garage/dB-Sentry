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
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT; // mic is 24-bit in 32-bit frame

  // Mono, RIGHT channel (LR pin pulled high)
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT;

  // On newer ESP32 cores, this combo works better than STAND_I2S
  cfg.communication_format = (i2s_comm_format_t)(
      I2S_COMM_FORMAT_STAND_I2S | I2S_COMM_FORMAT_STAND_MSB
  );

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

  // Mono clock
  i2s_set_clk(I2S_PORT, SAMPLE_RATE, I2S_BITS_PER_SAMPLE_32BIT, I2S_CHANNEL_MONO);
}

// ========================
// Self-test for the mic
// ========================
//
// Returns true if I2S data looks "alive" (not all zeros / identical),
// false if something seems wrong (no data or all the same).
//
bool selfTestMic() {
  const size_t TEST_SAMPLES = 512;
  int32_t buf[TEST_SAMPLES];
  size_t bytesRead = 0;

  // Clear DMA so we don’t read stale data
  i2s_zero_dma_buffer(I2S_PORT);

  esp_err_t res = i2s_read(
      I2S_PORT,
      (void *)buf,
      sizeof(buf),
      &bytesRead,
      1000 / portTICK_PERIOD_MS   // 1s timeout
  );

  if (res != ESP_OK) {
    Serial.print("I2S read error: ");
    Serial.println((int)res);
    return false;
  }

  if (bytesRead == 0) {
    Serial.println("I2S read returned 0 bytes – check clock/pins.");
    return false;
  }

  size_t n = bytesRead / sizeof(int32_t);
  if (n == 0) {
    Serial.println("I2S read had no samples – check config.");
    return false;
  }

  // Check if all raw samples are identical (usually means no valid data)
  int32_t first = buf[0];
  bool allSame = true;
  for (size_t i = 1; i < n; ++i) {
    if (buf[i] != first) {
      allSame = false;
      break;
    }
  }

  if (allSame) {
    Serial.print("All I2S samples identical (0x");
    Serial.print(first, HEX);
    Serial.println(") – mic likely not outputting.");
    return false;
  }

  // Optional: compute a small RMS on the RIGHT channel words
  // With I2S_CHANNEL_FMT_RIGHT_LEFT, memory layout is: R, L, R, L, ...
  double sumSq = 0.0;
  size_t count = 0;
  for (size_t i = 0; i + 1 < n; i += 2) {   // RIGHT channel at indices 0,2,4,...
    int32_t s = buf[i] >> 8;               // ICS-43432 uses top 24 bits
    sumSq += (double)s * (double)s;
    count++;
  }

  if (count == 0) {
    Serial.println("No right-channel samples – check LR pin and channel format.");
    return false;
  }

  double rms = sqrt(sumSq / (double)count);
  if (rms < 10.0) {  // Arbitrary low threshold
    Serial.println("Very low RMS from mic – might just be very quiet or miswired.");
    // Still return true, but warn.
    return true;
  }

  Serial.println("Mic self-test passed: I2S data looks alive.");
  return true;
}


// ========================
// Measurement: dBFS + approx dB SPL
// ========================
// Returns approx dB SPL, writes dBFS to dBFS_out
//
float measureLevel(float &dBFS_out) {
    int32_t samples[SAMPLE_COUNT];
    size_t bytesRead = 0;

    // Don't overuse zero_dma_buffer; just read
    esp_err_t res = i2s_read(
        I2S_PORT,
        (void *)samples,
        sizeof(samples),
        &bytesRead,
        portMAX_DELAY
    );

    if (res != ESP_OK || bytesRead == 0) {
        Serial.print("i2s_read error="); Serial.print((int)res);
        Serial.print(" bytesRead="); Serial.println(bytesRead);
        dBFS_out = -120.0f;
        return -120.0f;
    }

    size_t n = bytesRead / sizeof(int32_t);
    if (n == 0) {
        Serial.println("No samples!");
        dBFS_out = -120.0f;
        return -120.0f;
    }

    double sumSq = 0.0;
    size_t count = 0;

    // Mono: every word is a right-channel sample, 24-bit left-justified in 32 bits
    for (size_t i = 0; i < n; ++i) {
        int32_t s = samples[i] >> 8;   // keep top 24 bits, sign-extended
        sumSq += (double)s * (double)s;
        count++;
    }

    if (count == 0) {
        dBFS_out = -120.0f;
        return -120.0f;
    }

    double rms = sqrt(sumSq / (double)count);

    // Debug: print a bit so we can see it's non-zero
    Serial.print("bytesRead="); Serial.print(bytesRead);
    Serial.print(" samples="); Serial.print(n);
    Serial.print(" rms="); Serial.println(rms);

    if (rms <= 0.0) {
        dBFS_out = -120.0f;
        return -120.0f;
    }

    const double max24 = (double)((1 << 23) - 1);
    double dBFS = 20.0 * log10(rms / max24);
    dBFS_out = (float)dBFS;

    double dBSPL = dBFS + 120.0;  // rough mapping for ICS-43432
    return (float)dBSPL;
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

  Serial.println("Running mic self-test...");
  if (!selfTestMic()) {
    Serial.println("Mic NOT responding – check wiring, pins, and LR pin state.");
  } else {
    Serial.println("Mic appears to be responding.");
  }
}

void loop() {
  uint32_t now = millis();

  if (now - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = now;

    float dBFS = 0.0f;
    float dBSPL = measureLevel(dBFS);

    Serial.print("Level: ");
    Serial.print(dBSPL, 1);
    Serial.print(" dB SPL approx (");
    Serial.print(dBFS, 1);
    Serial.println(" dBFS)");
  }

  // Do other work here if you like
}