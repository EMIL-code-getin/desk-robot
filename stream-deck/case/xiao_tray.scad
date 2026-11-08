// Adapter tray: holds a Seeed XIAO ESP32C3 (or C6) in the board pocket of the
// "Macropad" housing from MakerWorld, which was made for a DFRobot Beetle
// RP2350 (25 x 20.5 mm). The XIAO is smaller (21 x 17.8 mm), so this tray
// fills the gap, pushes the XIAO against the back wall and lifts it so its
// USB-C port lines up with the hole in the housing.
//
// Measured from the housing: pocket 20.9 mm wide, 25.2 mm from its front wall
// to the back wall of the housing, 3 mm high walls; USB hole 10.5 x 4.5 mm,
// 1.05-5.5 mm above the floor.
//
// Print flat, as oriented, no supports. Drop it into the pocket with the open
// end towards the USB hole, then press the XIAO in from above (USB-C first).

/* [Pocket in the housing] */
pocket_w = 20.9;
pocket_l = 25.2;
clear = 0.15;            // play around the tray in the pocket

/* [Board] */
board_w = 17.8;          // XIAO: width across the USB end
board_l = 21.0;
board_t = 1.0;           // PCB thickness
board_clear = 0.15;
// Raises the XIAO so the USB-C plug is centred in the hole. If the plug hits
// the top of the hole, lower this; if it hits the bottom, raise it.
lift = 1.0;
rim = 1.0;               // how far the walls rise above the PCB's underside

$fn = 32;

tray_w = pocket_w - 2*clear;
tray_l = pocket_l - 2*clear;
tray_h = lift + rim;

bw = board_w + 2*board_clear;
bl = board_l + board_clear;

difference() {
  // Body, with the back end (y = tray_l) towards the USB hole.
  hull() for (x = [0.8, tray_w - 0.8], y = [0.8, tray_l - 0.8])
    translate([x, y, 0]) cylinder(r = 0.8, h = tray_h);

  // XIAO pocket, open at the back so the USB-C port reaches the wall.
  translate([(tray_w - bw)/2, tray_l - bl, lift]) cube([bw, bl + 1, tray_h]);

  // Finger notch at the front to lift the XIAO out again.
  translate([tray_w/2, tray_l - bl, lift]) cylinder(d = 8, h = tray_h);

  // Text on the floor of the pocket.
  translate([tray_w/2, tray_l - bl/2, lift - 0.4])
    rotate(90) linear_extrude(1) text("USB ->", size = 3, halign = "center", valign = "center");
}
