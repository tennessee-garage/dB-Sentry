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

#include "StatusLED.h"

// ---------- CONFIG ----------

const int I2S_WS_PIN  = D2;   // LRCLK / WS
const int I2S_SCK_PIN = D1;   // BCLK / SCK
const int I2S_SD_PIN  = D0;   // SD (data from mic)

const int LED_STATUS_PIN = D3;  // On-board LED
const int LED_DATA_PIN   = D5;  // Additional LED for data activity
const int LED_ALERT_PIN  = D4;  // Additional LED for alerts

// ---------- OBJECTS ----------

Logger *LOGGER = nullptr;
MQTT *mqtt = nullptr;

MEMS *memsMic = nullptr;
FFTTransform *fftTransform = nullptr;

BandLevel *bassBand = nullptr;
BandLevel *midBand = nullptr;
BandLevel *trebleBand = nullptr;

StatusLED *statusLED = nullptr;

// ---------- SETUP ----------
void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.println("Starting I2S + FFT test…");

    statusLED = new StatusLED(LED_STATUS_PIN, LED_DATA_PIN, LED_ALERT_PIN);
    statusLED->begin();

    // Run through all the LEDs to test them
    statusLED->blinkOnceBlocking(StatusLED::STATUS, 500);
    statusLED->blinkOnceBlocking(StatusLED::DATA, 500);
    statusLED->blinkOnceBlocking(StatusLED::ALERT, 500);

    // Start a slow blink during WiFi setup
    statusLED->blinkContinuous(StatusLED::STATUS, 100, 500);

    LOGGER = new Logger();
    LOGGER->init(SYSLOG_SERVER, SYSLOG_PORT, HOSTNAME, APP_NAME);

    const char *creds[] = WIFI_CREDENTIALS_LIST;
    WirelessControl::init_wifi_from_list(creds, HOSTNAME);

    if (!WirelessControl::is_connected) {
        // Fast blink on alert LED
        statusLED->blinkContinuous(StatusLED::ALERT, 100, 100);
        // Fatal error, halt here
        while (1);
    }

    statusLED->on(StatusLED::STATUS); // Solid ON when WiFi connected

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
        statusLED->blinkOnce(StatusLED::DATA, 50); // Blink data LED on report

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