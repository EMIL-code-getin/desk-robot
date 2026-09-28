# Joystick H-shifter (Arduino Uno)

A side project, separate from the robot: turn a cheap 2-axis thumb joystick
(KY-023 or any PS2-style module) into a 6-speed + reverse H-pattern shifter
on an Arduino Uno.

```
    1   3   5
    |   |   |
    +---N---+
    |   |   |
    2   4   6/R
```

## Wiring

| Joystick | Uno |
|----------|-----|
| VCC / +5V | 5V |
| GND | GND |
| VRx | A0 |
| VRy | A1 |
| SW | D2 |

No resistors needed: the button uses the Uno's internal pull-up.

## Use it

1. Open `h_shifter/h_shifter.ino` in the Arduino IDE, pick **Arduino Uno**,
   and upload.
2. **Leave the stick centered while the board starts.** It averages the
   resting position for about 130 ms to find the center.
3. Open the Serial Monitor at **115200 baud**. You'll see `Gear: N`, then
   `Gear: 1`, `Gear: 2` and so on as you shift. The built-in LED is on in
   any gear and off in neutral.

**How it shifts:**

- Left/right picks the column, but only in neutral, so you can't jump from
  1 to 5 without going through the middle, just like a real gearbox.
- Push up or down past the gate to go into gear. It stays in gear until the
  stick is back near the center line, so it won't flicker at the edge.
- **Reverse:** hold the stick's push button down while going into the
  bottom-right slot. Without the button, that slot is 6th.

## Settings

Everything is at the top of the sketch:

| Setting | What it does |
|---------|--------------|
| `INVERT_X`, `INVERT_Y` | Flip an axis if the gears come out mirrored. |
| `COLUMN_THRESHOLD` | How far left/right selects the outer columns. |
| `ENGAGE_THRESHOLD` / `RELEASE_THRESHOLD` | How far up/down to go into gear, and how far back to drop out of it. Keep release below engage. |
| `REVERSE_NEEDS_BUTTON` | `false` makes it a 5-speed with R in the bottom-right, no button. |
| `PLAIN_OUTPUT` | `true` prints just `N`, `1`…`6`, `R`, for another program reading the serial port. |
| `GEAR_LED_PINS` | Pins for one LED per gear (N, 1–6, R); `0` means none. Use a 220 Ω resistor per LED. |

## Using it in PC games

The Uno's USB chip can't act as a game controller or keyboard out of the
box, so the Uno version reports the gear over serial. To shift in a racing
game you have two options:

- **Use a Leonardo, Micro or Pro Micro** (ATmega32U4, native USB) with the
  [ArduinoJoystickLibrary](https://github.com/MHeironimus/ArduinoJoystickLibrary)
  and press one button per gear where `showGear()` runs.
- **Keep the Uno** and read the serial output on the PC with a small script
  that sends key presses, or flash the Uno's USB chip with
  [UnoJoy](https://github.com/AlanChatham/UnoJoy).
