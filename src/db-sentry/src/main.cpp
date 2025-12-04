#include <Arduino.h>
#include <driver/i2s.h>
#include <arduinoFFT.h>

#include "main.h"
#include "wifi-info.h"

#include <Logger.h>
#include "WirelessControl.h"
#include "MQTT.h"

#include "MEMS.h"
#include "FFTTransform.h"
#include "BandLevel.h"

// ---------- CONFIG ----------

const int I2S_WS_PIN  = D2;   // LRCLK / WS
const int I2S_SCK_PIN = D1;   // BCLK / SCK
const int I2S_SD_PIN  = D0;   // SD (data from mic)

// ---------- OBJECTS ----------

Logger *LOGGER = nullptr;
MQTT *mqtt = nullptr;

MEMS *memsMic = nullptr;
FFTTransform *fftTransform = nullptr;

BandLevel *bassBand = nullptr;
BandLevel *midBand = nullptr;
BandLevel *trebleBand = nullptr;

// ---------- SETUP ----------
void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.println("Starting I2S + FFT test…");

    LOGGER = new Logger();
    LOGGER->init(SYSLOG_SERVER, SYSLOG_PORT, HOSTNAME, APP_NAME);

    const char *creds[] = WIFI_CREDENTIALS_LIST;
    WirelessControl::init_wifi_from_list(creds, HOSTNAME);

    mqtt = new MQTT(MQTT_SERVER);

    memsMic = new MEMS(I2S_SD_PIN, I2S_SCK_PIN, I2S_WS_PIN);
    fftTransform = new FFTTransform(memsMic);

    bassBand   = new BandLevel(fftTransform,   20.0f,   250.0f, 35.0f);   // 20–250 Hz
    midBand    = new BandLevel(fftTransform,  250.0f,  4000.0f, 47.0f);   // 250–4 kHz
    trebleBand = new BandLevel(fftTransform, 4000.0f,  8000.0f, 65.0f);   // 4–8 kHz (limited by Fs/2)
}

// ---------- MAIN LOOP ----------
uint32_t lastReportMs = 0;
void loop() {
    if (memsMic->readSamples()) {
        fftTransform->process();

        Serial.printf(">bass:%.1f\n>mid:%.1f\n>treble:%.1f\n",
          bassBand->computeSmoothedLevel(),
          midBand->computeSmoothedLevel(),
          trebleBand->computeSmoothedLevel()
        );
    }

    mqtt->loop();

    uint32_t now = millis();
    if (now - lastReportMs >= LEQ_INTERVAL_MS) {
        // Report LEQ and max levels to InfluxDB
        mqtt->publishBandLevel("bass",   bassBand->leqLevel());
        mqtt->publishBandLevel("mid",    midBand->leqLevel());
        mqtt->publishBandLevel("treble", trebleBand->leqLevel());

        // Reset SPL computations
        bassBand->resetSPLComputation();
        midBand->resetSPLComputation();
        trebleBand->resetSPLComputation();
        lastReportMs = now;
    }
}