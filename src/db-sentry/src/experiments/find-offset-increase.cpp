#include <Arduino.h>
#include <driver/i2s.h>
#include <arduinoFFT.h>

#include "MEMS.h"

MEMS *memsMic;

// ---------- CONFIG ----------
#define I2S_PORT        I2S_NUM_0

// Set these to match your wiring:
const int I2S_WS_PIN  = D2;   // LRCLK / WS
const int I2S_SCK_PIN = D1;   // BCLK / SCK
const int I2S_SD_PIN  = D0;   // SD (data from mic)

// Audio & FFT params
#define FFT_BIN_COUNT   (SAMPLES / 2)
#define SAMPLES 1024
#define SAMPLE_RATE 48000

#define CAL_OFFSET_DB 0.0f //85.0f   // dB offset to calibrate dBFS to dB SPL

double vReal[SAMPLES];
double vImag[SAMPLES];

// Templated FFT instance with double precision
ArduinoFFT<double> FFT(vReal, vImag, SAMPLES, SAMPLE_RATE);

// Simple smoothed band levels
float bassLevel   = 0;
float midLevel    = 0;
float trebleLevel = 0;

// Smoothing factor for the meter (0=no smoothing, 1=very slow)
const float SMOOTHING = 0.7f;

// ---------- I2S SETUP ----------
void setupI2S() {
	i2s_config_t i2s_config = {
		.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
		.sample_rate = SAMPLE_RATE,
		.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
		.channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT, // mono
		.communication_format = I2S_COMM_FORMAT_I2S,
		.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
		.dma_buf_count = 4,
		.dma_buf_len = 256,
		.use_apll = false,
		.tx_desc_auto_clear = false,
		.fixed_mclk = 0
	};

	i2s_pin_config_t pin_config = {
		.bck_io_num = I2S_SCK_PIN,
		.ws_io_num = I2S_WS_PIN,
		.data_out_num = -1,       // not used (RX only)
		.data_in_num = I2S_SD_PIN
	};

	i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
	i2s_set_pin(I2S_PORT, &pin_config);
	i2s_zero_dma_buffer(I2S_PORT);

	// If your mic requires a specific I2S format (left-justified, etc.)
	// you might need i2s_set_clk or a different comm_format.
}

// ---------- BAND UTILS ----------
int freqToBin(float freq) {
  // bin index = freq / (Fs / N)
  float binWidth = (float)SAMPLE_RATE / (float)SAMPLES;
  int bin = (int)(freq / binWidth);
  if (bin < 0) bin = 0;
  if (bin >= FFT_BIN_COUNT) bin = FFT_BIN_COUNT - 1;
  return bin;
}

float computeBandLevel(double *spectrum, float fLow, float fHigh) {
  int iLow  = freqToBin(fLow);
  int iHigh = freqToBin(fHigh);

  // Skip bin 0 if iLow calculates to that, which includes DC offset
  if (iLow < 1) iLow = 1;
  // Ensure high is always greater than low
  if (iHigh <= iLow) iHigh = iLow + 1;
  // Make sure we don't go out of bounds in the spectrum array
  if (iHigh > FFT_BIN_COUNT - 1) iHigh = FFT_BIN_COUNT - 1;

  double sum = 0;
  for (int i = iLow; i <= iHigh; i++) {
    sum += spectrum[i];
  }

  float avg = (float)(sum / (double)(iHigh - iLow + 1));

  // Optionally convert to "dB-ish" scale
  // Avoid log(0)
  if (avg < 1e-12f) avg = 1e-12f;
  float db = 20.0f * log10f(avg);

  return db;
}

// Assumes:
//   #define SAMPLES 1024
//   #define FFT_BIN_COUNT (SAMPLES / 2)
//   #define SAMPLE_RATE 48000
//   int freqToBin(float freq) is defined as in your file.

float computeSPLBandLevel(const double *spectrum,
                          float fLow,
                          float fHigh,
                          float offset_dB)   // calibration offset: dBFS -> dB SPL
{
  // Convert frequency range to bin indices
  int iLow  = freqToBin(fLow);
  int iHigh = freqToBin(fHigh);

  // Skip DC bin (0) – gets rid of DC offset / bias
  if (iLow < 1) iLow = 1;

  // Ensure iHigh is at least one bin above iLow
  if (iHigh <= iLow) {
    iHigh = iLow + 1;
  }

  // Clamp to valid spectrum range
  if (iHigh > FFT_BIN_COUNT - 1) {
    iHigh = FFT_BIN_COUNT - 1;
  }

  int binCount = iHigh - iLow + 1;
  if (binCount <= 0) {
    // Shouldn't happen with the guards above, but just in case:
    return -160.0f; // effectively "silence"
  }

  // Compute RMS magnitude in this band
  double sumSq = 0.0;
  for (int i = iLow; i <= iHigh; i++) {
    double m = spectrum[i];
    sumSq += m * m;
  }

  double rms = sqrt(sumSq / (double)binCount);

  // Avoid log(0)
  const double EPS = 1e-12;
  if (rms < EPS) rms = EPS;

  // Convert to dBFS (relative to your normalized scale)
  float dBFS = 20.0f * log10f((float)rms);

  // Apply calibration offset to get dB SPL
  // (offset_dB = known_dBSPL_at_calibration - measured_dBFS_at_calibration)
  float dBSPL = dBFS + offset_dB;

  return dBSPL;
}

// ---------- SETUP ----------
void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("Starting I2S + FFT test…");

	memsMic = new MEMS(I2S_SD_PIN, I2S_SCK_PIN, I2S_WS_PIN);
}

// ---------- MAIN LOOP ----------
void loop() {

	if (memsMic->readSamples()) {
		for (size_t i = 0; i < memsMic->totalSamples(); i++) {
			vReal[i] = memsMic->samples[i];
			vImag[i] = 0.0;
		}

		// 2) Windowing
		FFT.windowing(vReal, SAMPLES, FFT_WIN_TYP_HAMMING, FFT_FORWARD);

		// 3) FFT
		FFT.compute(vReal, vImag, SAMPLES, FFT_FORWARD);

		// 4) Complex to magnitude
		FFT.complexToMagnitude(vReal, vImag, SAMPLES);

		// vReal now contains magnitude spectrum, bins 0..(SAMPLES/2 - 1) are useful

		// 5) Compute band levels
		float bass   = computeSPLBandLevel(vReal,   20.0f,   250.0f, 35.0f);   // 20–250 Hz
		float mids   = computeSPLBandLevel(vReal,  250.0f,  4000.0f, 47.0f);   // 250–4 kHz
		float treble = computeSPLBandLevel(vReal, 4000.0f,  8000.0f, 65.0f);   // 4–8 kHz (limited by Fs/2)

		// 6) Smooth for display / stability
		bassLevel   = SMOOTHING * bassLevel   + (1.0f - SMOOTHING) * bass;
		midLevel    = SMOOTHING * midLevel    + (1.0f - SMOOTHING) * mids;
		trebleLevel = SMOOTHING * trebleLevel + (1.0f - SMOOTHING) * treble;

		Serial.printf(">bass:%.1f\n>mid:%.1f\n>treble:%.1f\n", bassLevel, midLevel, trebleLevel);
	}
}