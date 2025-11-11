#include "MEMS.h"

MEMS::MEMS(uint8_t dataPin, uint8_t clockPin, uint8_t wordSelectPin)
	: _dataPin(dataPin), _clockPin(clockPin), _wordSelectPin(wordSelectPin) {
	// Constructor implementation (if needed)

	_setupI2S();
}

void MEMS::_setupI2S() {
	i2s_config_t i2s_config = {
		.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
		.sample_rate = SAMPLE_RATE,
		.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
		.channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT, // mono
		.communication_format = I2S_COMM_FORMAT_STAND_I2S,
		.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
		.dma_buf_count = 4,
		.dma_buf_len = 256,
		.use_apll = false,
		.tx_desc_auto_clear = false,
		.fixed_mclk = 0
	};

	i2s_pin_config_t pin_config = {
		.bck_io_num = _clockPin,
		.ws_io_num = _wordSelectPin,
		.data_out_num = -1,       // not used (RX only)
		.data_in_num = _dataPin
	};

	i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
	i2s_set_pin(I2S_PORT, &pin_config);
	i2s_zero_dma_buffer(I2S_PORT);
}

void MEMS::setSampleRate(uint32_t sampleRate) {
	// TODO: need to test this to make sure I2S_CHANNEL_MONO here works the same as
	// I2S_CHANNEL_FMT_ONLY_RIGHT in the main setup, since I don't understand how they align
	i2s_set_clk(I2S_PORT, sampleRate, I2S_BITS_PER_SAMPLE_32BIT, I2S_CHANNEL_MONO);
}

bool MEMS::readSamples() {
	for (int i = 0; i < SAMPLES; i++) {
    	int32_t raw = 0;
    	size_t bytesRead = 0;

		// Blocking read for one sample. For more control, use a buffer & non-blocking pattern.
		esp_err_t err = i2s_read(I2S_PORT, &raw, sizeof(raw), &bytesRead, portMAX_DELAY);
		if (err != ESP_OK || bytesRead == 0) {
			// If something goes wrong, just retry this index
			i--;
			continue;
		}

		// Most I2S MEMS mics give 24-bit data in the top 24 bits of this 32-bit word.
		int32_t sample24 = raw >> 8;  // sign-extended

		// Normalize to roughly -1..+1 (24-bit signed range)
		samples[i] = (double)sample24 / 8388608.0; // 2^23
	}

	return true;
}

uint16_t MEMS::totalSamples() {
	return SAMPLES;
}

uint32_t MEMS::sampleRate() {
	return SAMPLE_RATE;
}