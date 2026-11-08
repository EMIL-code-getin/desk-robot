// HID usage codes used in the keymap (config.h).
//
// Keyboard codes are *physical key positions* (USB HID usage page 0x07). The
// computer's keyboard layout decides which character a key produces, so on a
// Swedish layout KEY_SEMICOLON gives "ö", KEY_MINUS gives "+", and so on.
#pragma once
#include <stdint.h>

// ---- Modifiers (bit mask, combine with |) ---------------------------------
#define MOD_CTRL   0x01
#define MOD_SHIFT  0x02
#define MOD_ALT    0x04
#define MOD_GUI    0x08  // Windows key / Cmd on macOS
#define MOD_RCTRL  0x10
#define MOD_RSHIFT 0x20
#define MOD_ALTGR  0x40  // right Alt; AltGr on Nordic layouts
#define MOD_RGUI   0x80

// ---- Letters and digits ---------------------------------------------------
#define KEY_A 0x04
#define KEY_B 0x05
#define KEY_C 0x06
#define KEY_D 0x07
#define KEY_E 0x08
#define KEY_F 0x09
#define KEY_G 0x0A
#define KEY_H 0x0B
#define KEY_I 0x0C
#define KEY_J 0x0D
#define KEY_K 0x0E
#define KEY_L 0x0F
#define KEY_M 0x10
#define KEY_N 0x11
#define KEY_O 0x12
#define KEY_P 0x13
#define KEY_Q 0x14
#define KEY_R 0x15
#define KEY_S 0x16
#define KEY_T 0x17
#define KEY_U 0x18
#define KEY_V 0x19
#define KEY_W 0x1A
#define KEY_X 0x1B
#define KEY_Y 0x1C
#define KEY_Z 0x1D
#define KEY_1 0x1E
#define KEY_2 0x1F
#define KEY_3 0x20
#define KEY_4 0x21
#define KEY_5 0x22
#define KEY_6 0x23
#define KEY_7 0x24
#define KEY_8 0x25
#define KEY_9 0x26
#define KEY_0 0x27

// ---- Control and punctuation ----------------------------------------------
#define KEY_ENTER      0x28
#define KEY_ESC        0x29
#define KEY_BACKSPACE  0x2A
#define KEY_TAB        0x2B
#define KEY_SPACE      0x2C
#define KEY_MINUS      0x2D
#define KEY_EQUAL      0x2E
#define KEY_LEFTBRACE  0x2F
#define KEY_RIGHTBRACE 0x30
#define KEY_BACKSLASH  0x31
#define KEY_SEMICOLON  0x33
#define KEY_APOSTROPHE 0x34
#define KEY_GRAVE      0x35
#define KEY_COMMA      0x36
#define KEY_DOT        0x37
#define KEY_SLASH      0x38
#define KEY_CAPSLOCK   0x39
#define KEY_NONUS_BACKSLASH 0x64  // ISO key left of Z: < > | on Swedish layout

// ---- Function keys --------------------------------------------------------
// F13-F24 exist in the HID spec but not on normal keyboards, so they never
// collide with anything. Perfect for binding in OBS, Discord, AutoHotkey...
#define KEY_F1  0x3A
#define KEY_F2  0x3B
#define KEY_F3  0x3C
#define KEY_F4  0x3D
#define KEY_F5  0x3E
#define KEY_F6  0x3F
#define KEY_F7  0x40
#define KEY_F8  0x41
#define KEY_F9  0x42
#define KEY_F10 0x43
#define KEY_F11 0x44
#define KEY_F12 0x45
#define KEY_F13 0x68
#define KEY_F14 0x69
#define KEY_F15 0x6A
#define KEY_F16 0x6B
#define KEY_F17 0x6C
#define KEY_F18 0x6D
#define KEY_F19 0x6E
#define KEY_F20 0x6F
#define KEY_F21 0x70
#define KEY_F22 0x71
#define KEY_F23 0x72
#define KEY_F24 0x73

// ---- Navigation -----------------------------------------------------------
#define KEY_PRINTSCREEN 0x46
#define KEY_SCROLLLOCK  0x47
#define KEY_PAUSE       0x48
#define KEY_INSERT      0x49
#define KEY_HOME        0x4A
#define KEY_PAGEUP      0x4B
#define KEY_DELETE      0x4C
#define KEY_END         0x4D
#define KEY_PAGEDOWN    0x4E
#define KEY_RIGHT       0x4F
#define KEY_LEFT        0x50
#define KEY_DOWN        0x51
#define KEY_UP          0x52

// ---- Consumer / media keys (USB HID usage page 0x0C) ----------------------
#define MEDIA_NEXT        0x00B5
#define MEDIA_PREV        0x00B6
#define MEDIA_STOP        0x00B7
#define MEDIA_PLAY_PAUSE  0x00CD
#define MEDIA_MUTE        0x00E2
#define MEDIA_VOL_UP      0x00E9
#define MEDIA_VOL_DOWN    0x00EA
#define MEDIA_BRIGHT_UP   0x006F
#define MEDIA_BRIGHT_DOWN 0x0070
#define MEDIA_CALCULATOR  0x0192
#define MEDIA_MAIL        0x018A
#define MEDIA_BROWSER     0x0196  // "My computer"/file browser on Windows
#define MEDIA_WWW_HOME    0x0223
#define MEDIA_WWW_SEARCH  0x0221
