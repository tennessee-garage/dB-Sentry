#include "FFTTransform.h"

FFTTransform::FFTTransform(MEMS *mic) : _mic(mic) {
	vReal = new double[mic->totalSamples()];
	vImag = new double[mic->totalSamples()];

	// Templated FFT instance with double precision
	_FFT = ArduinoFFT<double>(vReal, vImag, mic->totalSamples(), mic->sampleRate());
}

void FFTTransform::process() {
	memcpy(vReal, _mic->samples, _mic->totalSamples() * sizeof(double));
	memset(vImag, 0, _mic->totalSamples() * sizeof(double));

    // 2) Windowing
	_FFT.windowing(vReal, _mic->totalSamples(), FFT_WIN_TYP_HAMMING, FFT_FORWARD);

    // 3) FFT
	_FFT.compute(vReal, vImag, _mic->totalSamples(), FFT_FORWARD);

	// 4) Complex to magnitude
	_FFT.complexToMagnitude(vReal, vImag, _mic->totalSamples());
}

uint16_t FFTTransform::totalSamples() {
	return _mic->totalSamples();
}

uint32_t FFTTransform::sampleRate() {
	return _mic->sampleRate();
}