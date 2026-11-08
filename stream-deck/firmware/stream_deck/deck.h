// The stream deck program. Kept out of the .ino so the Arduino IDE does not
// rewrite it (it adds function prototypes to .ino files, which breaks code
// inside namespaces).
#pragma once

namespace deck {
void setup();
void loop();
}  // namespace deck
