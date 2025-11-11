#ifndef MEMS_H
#define MEMS_H

#include <Arduino.h>
#include <driver/i2s.h>

#define I2S_PORT I2S_NUM_0

// How many samples to collect before processing
#define SAMPLES 1024
#define SAMPLE_RATE 48000

// Ths is 2^23, used for normalizing 24-bit signed samples
#define MAX_23_BIT_SIGNED 8388608.0

#define READ_TIMEOUT_MS 200
#define READ_TIMEOUT_TICKS (READ_TIMEOUT_MS / portTICK_PERIOD_MS)

class MEMS {
public:
	double samples[SAMPLES];

	MEMS(uint8_t dataPin, uint8_t clockPin, uint8_t wordSelectPin);
	void setSampleRate(uint32_t sampleRate);
	bool readSamples();
	uint16_t totalSamples();
	uint32_t sampleRate();

private:
	uint8_t _dataPin;
	uint8_t _clockPin;
	uint8_t _wordSelectPin;

	uint16_t _samplesRead = 0;

	void _setupI2S();
};

#endif // MEMS_H
