#ifndef STATUSLED_H
#define STATUSLED_H

#include <Arduino.h>

class StatusLED {
public:
    enum LEDType {
        STATUS = 0,
        DATA = 1,
        ALERT = 2
    };

    // Constructor: initialize with GPIO pins for status, data, and alert LEDs
    StatusLED(uint8_t status_pin, uint8_t data_pin, uint8_t alert_pin);

    // Initialize the pins and start background task (call in setup())
    void begin();

    // Stop the background task and cleanup (call before destroying object)
    void end();

    // Turn LED on
    void on(LEDType led);

    // Turn LED off (also cancels continuous blinking)
    void off(LEDType led);

    // Blink once for specified duration (async)
    void blinkOnce(LEDType led, uint32_t duration_ms);

    // Blink once for specified duration (blocking/synchronous)
    void blinkOnceBlocking(LEDType led, uint32_t duration_ms);

    // Blink continuously with specified duty cycle (async)
    void blinkContinuous(LEDType led, uint32_t on_ms, uint32_t off_ms);

private:
    TaskHandle_t taskHandle;
    static void blinkTask(void* parameter);
    void updateLEDs();
    struct LEDState {
        uint8_t pin;
        bool is_on;
        bool blink_continuous;
        bool blink_once_active;
        uint32_t blink_on_time;
        uint32_t blink_off_time;
        uint32_t last_toggle_ms;
    };

    LEDState leds[3];

    void setPin(LEDType led, bool state);
};

#endif
