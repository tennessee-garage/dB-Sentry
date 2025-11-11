# Copilot / AI agent instructions — db-sentry (Xiao ESP32-C3, I2S mic)

Keep guidance short and actionable. This repo is a small PlatformIO/Arduino project that reads an I2S microphone (ICS-43432) on a Seeed Xiao ESP32-C3 and sends periodic level measurements to InfluxDB.  It's intended as a simple utility for monitoring sound levels in an outdoor environment.

Key files & locations
- `platformio.ini` — project/board and framework (board: `seeed_xiao_esp32c3`, framework: `arduino`).
- `src/main.cpp` — single main program: initiailizes I2S mic, collects samples and sends to influxcb.  A test mode ouputs Serial reporting.
- `src/experiments/` — scratch/test code for testing.
- `lib/`, `include/` — place for supporting libraries/headers (none required for basic work).
- `test/` — PlatformIO unit test runner scaffolding/notes.

Big-picture architecture (what to know quickly)
- Single MCU firmware project (no RTOS services beyond Arduino/ESP core). The code configures ESP32's I2S peripheral and reads 32-bit words containing 24-bit PCM from an ICS-43432 microphone.
- Data flow: I2S DMA -> int32_t sample buffer -> channel extraction (RIGHT is used) -> RMS/dBFS computation -> approximate dB SPL mapping -> Serial output.
- Why it’s structured this way: the code is intended as a small level-meter using FFTs to analyze frequency bands and send levels over the network to InfluxDB.

Project-specific conventions & patterns
- Pin constants use Arduino-style `D0 / D1 / D2` symbols in `src/main.cpp`. To change wiring, edit `I2S_WS_PIN`, `I2S_SCK_PIN`, `I2S_SD_PIN` near the top of `main.cpp`.
- The I2S layout uses `I2S_CHANNEL_FMT_RIGHT_LEFT`. Samples are read as 32-bit words; the mic uses the top 24 bits — code uses `>> 8` to convert to signed 24-bit values.
- RMS/dB calculation: `measureLevel()` computes RMS on the RIGHT channel samples and maps dBFS -> dB SPL with an approximate offset (+120). This is a rough mapping tied to the ICS-43432 sensitivity comment in the source.
- Error conventions: functions return sensible sentinel values (e.g., -120 dB) and print diagnostic lines to Serial.

Build / test / debug workflows (concrete commands)
- Build: `pio run` (uses `platformio.ini` env `seeed_xiao_esp32c3`).
- Upload: `pio run -e seeed_xiao_esp32c3 -t upload` (or use the PlatformIO IDE upload button).
- Monitor Serial (macOS zsh): `pio device monitor -b 115200` or `pio device monitor -p <port> -b 115200`. The code opens Serial at 115200.
- Verbose build: `pio run -v`.
- Unit tests: See `test/` and PlatformIO testing docs; run `pio test` to execute unit tests if added.

Integration & external dependencies
- PlatformIO (core) is required. Board: `espressif32` platform with `seeed_xiao_esp32c3` board support and the Arduino framework.
- Source includes `driver/i2s.h` — the code uses ESP-IDF headers via the Arduino core; be careful when changing low-level I2S config.

Safe edit patterns & examples
- To change sample rate: edit `SAMPLE_RATE` in `src/main.cpp` and adjust `SAMPLE_COUNT` if you want a specific time window.
- To switch LR channel mapping: if LR polarity changes, `I2S_CHANNEL_FMT_RIGHT_LEFT` or code that picks indices (0,2,4...) will need adjustment.
- To increase stability when reading: keep `i2s_zero_dma_buffer(I2S_PORT)` before reads as the source does.

What to avoid / gotchas
- Don’t reformat large unrelated files in the same commit — repository aims to keep diffs minimal.
- The dB SPL mapping is approximate; do not treat `dB_SPL ≈ dBFS + 120` as a calibrated measurement unless you add calibration code.
- Changing I2S constants (bits-per-sample, channel format) requires matching the mic config; otherwise reads may be all zeros/identical.

If you need to add tests
- Add small PlatformIO unit tests under `test/` that mock or simulate sample buffers and validate `measureLevel()` and `selfTestMic()` behaviors.

If anything here is unclear or you want other examples (e.g., adding calibration, integrating with MQTT), tell me which area to expand and I’ll update this file.

— end of Copilot instructions
