#include <Arduino.h>
#include <driver/i2s.h>
#include <arduinoFFT.h>

#include "MEMS.h"
#include "FFTTransform.h"
#include "BandLevel.h"

// ---------- CONFIG ----------

const int I2S_WS_PIN  = D2;   // LRCLK / WS
const int I2S_SCK_PIN = D1;   // BCLK / SCK
const int I2S_SD_PIN  = D0;   // SD (data from mic)

// ---------- OBJECTS ----------

MEMS *memsMic;
FFTTransform *fftTransform;

BandLevel *bassBand;
BandLevel *midBand;
BandLevel *trebleBand;

// ---------- SETUP ----------
void setup() {
	Serial.begin(115200);
	delay(200);
	Serial.println("Starting I2S + FFT test…");

	memsMic = new MEMS(I2S_SD_PIN, I2S_SCK_PIN, I2S_WS_PIN);
	fftTransform = new FFTTransform(memsMic);

	bassBand   = new BandLevel(fftTransform,   20.0f,   250.0f, 35.0f);   // 20–250 Hz
	midBand    = new BandLevel(fftTransform,  250.0f,  4000.0f, 47.0f);   // 250–4 kHz
	trebleBand = new BandLevel(fftTransform, 4000.0f,  8000.0f, 65.0f);   // 4–8 kHz (limited by Fs/2)
}

// ---------- MAIN LOOP ----------
void loop() {

	// This will not block, and will return true when enough samples are available
	if (memsMic->readSamples()) {
		fftTransform->process();

		Serial.printf(">bass:%.1f\n>mid:%.1f\n>treble:%.1f\n",
			bassBand->computeSmoothedLevel(),
			midBand->computeSmoothedLevel(),
			trebleBand->computeSmoothedLevel()
		);
	}
}