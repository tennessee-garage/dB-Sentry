#!/usr/bin/env python3
"""
Simple test script for a rotary encoder using gpiozero.

Usage:
  python scripts/test_encoder_gpiozero.py --a 17 --b 18 --btn 27

Requirements on Raspberry Pi:
  sudo apt install python3-gpiozero
  or: pip install gpiozero

This script prints rotation steps and button presses. It uses gpiozero's
RotaryEncoder (which uses pigpio if available but falls back to RPi.GPIO).
"""
import time
import argparse
import logging

try:
    from gpiozero import RotaryEncoder, Button
    from signal import pause
except Exception as e:
    raise SystemExit("gpiozero is required. Install with 'pip install gpiozero' or 'sudo apt install python3-gpiozero'")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--a', type=int, default=17, help='A / data pin (BCM)')
    p.add_argument('--b', type=int, default=18, help='B / clock pin (BCM)')
    p.add_argument('--btn', type=int, default=27, help='Button pin (BCM)')
    p.add_argument('--max', type=int, default=1000, help='Max steps (optional)')
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    log = logging.getLogger('test-encoder')

    log.info('Starting gpiozero encoder test (A=%d B=%d BTN=%d)', args.a, args.b, args.btn)

    encoder = RotaryEncoder(a=args.a, b=args.b, max_steps=args.max, wrap=False)
    button = Button(args.btn, pull_up=True, bounce_time=0.05)

    last_steps = encoder.steps

    def on_rotated():
        nonlocal last_steps
        steps = encoder.steps
        delta = steps - last_steps
        last_steps = steps
        direction = 'CW' if delta > 0 else 'CCW'
        log.info('Rotated: steps=%d delta=%+d dir=%s', steps, delta, direction)

    def on_pressed():
        log.info('Button pressed')

    encoder.when_rotated = on_rotated
    button.when_pressed = on_pressed

    try:
        # keep running; callbacks run in background threads
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info('Stopping test')
    finally:
        encoder.close()
        button.close()


if __name__ == '__main__':
    main()
