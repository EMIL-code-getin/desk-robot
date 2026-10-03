#!/usr/bin/env python3
# Stänger av Pi:n när PowerBoost 1000C:s LBO-pinne varit låg i 10 sekunder.
# LBO är kopplad via en Schottkydiod (katoden mot LBO) till GPIO26.
from gpiozero import Button
from signal import pause
import subprocess

lbo = Button(26, pull_up=True, hold_time=10)


def shutdown():
    subprocess.run(["wall", "Batteriet är nästan slut – stänger av!"])
    subprocess.run(["shutdown", "-h", "now"])


lbo.when_held = shutdown
pause()
