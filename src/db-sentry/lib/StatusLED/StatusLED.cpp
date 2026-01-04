#include "StatusLED.h"

StatusLED::StatusLED(uint8_t status_pin, uint8_t data_pin, uint8_t alert_pin) : taskHandle(NULL) {
    leds[STATUS].pin = status_pin;
    leds[DATA].pin = data_pin;
    leds[ALERT].pin = alert_pin;

    // Initialize state
    for (int i = 0; i < 3; i++) {
        leds[i].is_on = false;
        leds[i].blink_continuous = false;
        leds[i].blink_once_active = false;
        leds[i].blink_on_time = 0;
        leds[i].blink_off_time = 0;
        leds[i].last_toggle_ms = 0;
    }
}

void StatusLED::begin() {
    for (int i = 0; i < 3; i++) {
        pinMode(leds[i].pin, OUTPUT);
        digitalWrite(leds[i].pin, HIGH);  // HIGH = off (inverted logic for current-sinking)
    }
    
    // Create background task for blinking (priority 1, 2KB stack, core 0)
    xTaskCreatePinnedToCore(
        blinkTask,      // Task function
        "StatusLED",    // Task name
        2048,           // Stack size (bytes)
        this,           // Parameter passed to task
        1,              // Priority
        &taskHandle,    // Task handle
        0               // Core 0
    );
}

void StatusLED::end() {
    if (taskHandle != NULL) {
        vTaskDelete(taskHandle);
        taskHandle = NULL;
    }
}

void StatusLED::on(LEDType led) {
    // Cancel any blinking
    leds[led].blink_continuous = false;
    leds[led].blink_once_active = false;
    
    // Turn on
    setPin(led, true);
}

void StatusLED::off(LEDType led) {
    // Cancel any blinking
    leds[led].blink_continuous = false;
    leds[led].blink_once_active = false;
    
    // Turn off
    setPin(led, false);
}

void StatusLED::blinkOnce(LEDType led, uint32_t duration_ms) {
    // Cancel continuous blinking if active
    leds[led].blink_continuous = false;
    
    // Set up single blink
    leds[led].blink_once_active = true;
    leds[led].blink_on_time = duration_ms;
    leds[led].last_toggle_ms = millis();
    
    // Turn on immediately
    setPin(led, true);
}

void StatusLED::blinkOnceBlocking(LEDType led, uint32_t duration_ms) {
    // Cancel any active blinking
    leds[led].blink_continuous = false;
    leds[led].blink_once_active = false;
    
    // Turn on, wait, turn off
    setPin(led, true);
    delay(duration_ms);
    setPin(led, false);
}

void StatusLED::blinkContinuous(LEDType led, uint32_t on_ms, uint32_t off_ms) {
    // Cancel single blink if active
    leds[led].blink_once_active = false;
    
    // Set up continuous blinking
    leds[led].blink_continuous = true;
    leds[led].blink_on_time = on_ms;
    leds[led].blink_off_time = off_ms;
    leds[led].last_toggle_ms = millis();
    
    // Start with LED on
    setPin(led, true);
}

void StatusLED::blinkTask(void* parameter) {
    StatusLED* instance = static_cast<StatusLED*>(parameter);
    
    while (true) {
        instance->updateLEDs();
        vTaskDelay(10 / portTICK_PERIOD_MS);  // Check every 10ms
    }
}

void StatusLED::updateLEDs() {
    uint32_t now = millis();
    
    for (int i = 0; i < 3; i++) {
        LEDState &led = leds[i];
        
        // Handle single blink
        if (led.blink_once_active) {
            if (led.is_on && (now - led.last_toggle_ms >= led.blink_on_time)) {
                // Turn off and stop blinking
                setPin((LEDType)i, false);
                led.blink_once_active = false;
            }
        }
        
        // Handle continuous blinking
        if (led.blink_continuous) {
            uint32_t threshold = led.is_on ? led.blink_on_time : led.blink_off_time;
            
            if (now - led.last_toggle_ms >= threshold) {
                // Toggle state
                setPin((LEDType)i, !led.is_on);
                led.last_toggle_ms = now;
            }
        }
    }
}

void StatusLED::setPin(LEDType led, bool state) {
    leds[led].is_on = state;
    digitalWrite(leds[led].pin, state ? LOW : HIGH);  // Inverted: LOW turns LED on (sinking current)
}
