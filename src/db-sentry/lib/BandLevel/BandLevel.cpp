#include "BandLevel.h"

BandLevel::BandLevel(FFTTransform *fftTransform, float fLow, float fHigh, float offset_dB)
	: _fftTransform(fftTransform), _fLow(fLow), _fHigh(fHigh), _offset_dB(offset_dB) {
		_smoothing = SMOOTHING;
		_fft_bin_count = (_fftTransform->totalSamples()) / 2;
}

void BandLevel::setSmoothing(float smoothing) {
	_smoothing = smoothing;
}

int BandLevel::freqToBin(float freq) {
	// bin index = freq / (Fs / N)
	float binWidth = (float)_fftTransform->sampleRate() / (float)_fftTransform->totalSamples();
	int bin = (int)(freq / binWidth);
	if (bin < 0) bin = 0;
	if (bin >= _fft_bin_count) bin = _fft_bin_count - 1;
	return bin;
}

float BandLevel::computeBandLevel() {
	int iLow  = freqToBin(_fLow);
	int iHigh = freqToBin(_fHigh);

	// Skip bin 0 if iLow calculates to that, which includes DC offset
	if (iLow < 1) iLow = 1;
	// Ensure high is always greater than low
	if (iHigh <= iLow) iHigh = iLow + 1;
	// Make sure we don't go out of bounds in the spectrum array
	if (iHigh > _fft_bin_count - 1) iHigh = _fft_bin_count - 1;

	double sum = 0;
	for (int i = iLow; i <= iHigh; i++) {
		sum += _fftTransform->vReal[i];
	}

	float avg = (float)(sum / (double)(iHigh - iLow + 1));

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

float BandLevel::computeSPLBandLevel()
{
	// Convert frequency range to bin indices
	int iLow  = freqToBin(_fLow);
	int iHigh = freqToBin(_fHigh);

	// Skip DC bin (0) – gets rid of DC offset / bias
	if (iLow < 1) iLow = 1;

	// Ensure iHigh is at least one bin above iLow
	if (iHigh <= iLow) {
		iHigh = iLow + 1;
	}

	// Clamp to valid spectrum range
	if (iHigh > _fft_bin_count - 1) {
		iHigh = _fft_bin_count - 1;
	}

	int binCount = iHigh - iLow + 1;
	if (binCount <= 0) {
		// Effectively "silence"; shouldn't happen with the guards above, but just in case
		return -160.0f; 
	}

	// Compute RMS magnitude in this band
	double sumSq = 0.0;
	for (int i = iLow; i <= iHigh; i++) {
		double m = _fftTransform->vReal[i];
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
	float dBSPL = dBFS + _offset_dB;

	return dBSPL;
}

float BandLevel::computeSmoothedLevel() {
	float current_level = computeSPLBandLevel();
	float smoothed_level = _smoothing * _prev_level + (1.0f - _smoothing) * current_level;
	_prev_level = smoothed_level;

	double lin = pow(10.0, smoothed_level / 10.0);
	_sumLin += lin;
	_sampleCount++;
	if (smoothed_level > _maxDb) {
		_maxDb = smoothed_level;
	}

	return smoothed_level;
}

float BandLevel::leqLevel() {
	if (_sampleCount == 0) {
		return -160.0f; // effectively "silence"
	}
	double avgLin = _sumLin / (double)_sampleCount;
	float leqDb = 10.0f * log10f((float)avgLin);
	return leqDb;
}

float BandLevel::maxSPLLevel() {
	return _maxDb;
}

void BandLevel::resetSPLComputation() {
	_sumLin = 0.0;
	_sampleCount = 0;
	_maxDb = -160.0f;
}