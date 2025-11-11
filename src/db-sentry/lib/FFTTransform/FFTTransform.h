#ifndef FFTTRANSFORM_H
#define FFTTRANSFORM_H

#include <Arduino.h>
#include <arduinoFFT.h>
#include "MEMS.h"

class FFTTransform {
public:
	double *vReal = nullptr;
	double *vImag = nullptr;

	FFTTransform(MEMS *mic);
	void process();
	uint16_t totalSamples();
	uint32_t sampleRate();
	
private:	
	ArduinoFFT<double> _FFT;
	MEMS *_mic;
};

#endif // FFTTRANSFORM_H
