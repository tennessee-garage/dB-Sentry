#include <Arduino.h>

void setup() {
  pinMode(D6, OUTPUT);
}
void loop() {
  digitalWrite(D6, HIGH);
  delay(200);
  digitalWrite(D6, LOW);
  delay(200);
}