#ifndef BANDLEVEL_H
#define BANDLEVEL_H

#include <Arduino.h>
#include "FFTTransform.h"

// Smoothing factor for the meter (0=no smoothing, 1=very slow)
const float SMOOTHING = 0.7f;

class BandLevel {
public:

	BandLevel(FFTTransform *fftTransform, float fLow, float fHigh, float offset_dB);
	void setSmoothing(float smoothing);
	void compute();

	int freqToBin(float freq);
	float computeBandLevel();
	float computeSPLBandLevel();
	float computeSmoothedLevel();

	float leqLevel();
	float maxSPLLevel();
	void resetSPLComputation();
	
private:	
	FFTTransform *_fftTransform = nullptr;
	float _fLow;
	float _fHigh;
	float _offset_dB;
	float _smoothing = SMOOTHING;

	uint16_t _fft_bin_count;

	float _prev_level = 0.0f;

	// For SPL computation
	double _sumLin = 0.0;
	uint16_t _sampleCount = 0;
	float _maxDb = -160.0f;
};

#endif // BANDLEVEL_H