// Stream deck case: 6 MX-style keys (3 x 2) + EC11 rotary encoder,
// ESP32-C6 board (default: Seeed XIAO ESP32C6) inside, USB-C at the back.
//
// Parts (choose with `part`, or use the ready STLs in stl/):
//   "top"    shell with switch plate. Print upside down (flat top on the bed),
//            no supports needed.
//   "bottom" base plate with board cradle. Print as oriented, no supports.
//   "riser"  rear bar that tilts the deck ~5 degrees. Optional.
//   "knob"   encoder knob for a D-shaft. Print top down, no supports.
//   "assembly" preview of everything together (not for printing).
//
// Render STLs from the command line:
//   openscad -D 'part="top"' -o stl/top.stl stream_deck.scad
//
// Hardware: 2x M3x8 + 2x M3x12 screws (M3x12 at the back go through the
// riser; without the riser use 4x M3x8). Self-tapping into the plastic, or set
// insert_holes = true for M3 heat-set inserts. 4x rubber feet up to 10 mm.

part = "assembly";  // "top", "bottom", "riser", "knob", "assembly"

/* [Layout] */
pitch = 19.05;            // MX key spacing
cols = 3;
rows = 2;
enc_gap = 29;             // key column 3 centre -> encoder centre (mm)
edge = 8;                 // key-unit edge -> outer wall (mm)
enc_edge = 9;             // knob radius -> outer wall (mm)

/* [Shell] */
wall = 2.4;
top_t = 3.0;              // top thickness (stiff), thinned to plate_t at switches
plate_t = 1.5;            // MX clips need a 1.5 mm plate
enc_plate_t = 1.6;        // EC11 bushing has ~5 mm of thread; keep this thin
inner_h = 20;             // free height between base plate and underside of top
corner_r = 4;
bot_t = 2.4;              // base plate thickness

/* [Switch & encoder cut-outs] */
sw_hole = 14.0;           // MX plate cut-out (14.0 standard; 14.1 if tight)
sw_pocket = 15.6;         // underside pocket so the clips catch a 1.5 mm plate
enc_hole = 7.4;           // EC11 M7 bushing
enc_pocket = 13.4;        // EC11 body clearance on the underside
enc_tab = false;          // blind slot for the EC11 anti-rotation tab; by
                          // default snap the tab off with pliers instead
led_hole = 3.2;           // optional 3 mm status LED, 0 = none

/* [Board] */
// Seeed XIAO ESP32C6: 17.8 mm across the USB-C end, 21 mm long. For another
// board, measure it and put width (across the USB port) and length here.
board_w = 17.8;
board_l = 21.0;
board_x = 19.05;          // board centre, X (same coordinates as the keys)
usb_w = 13.0;             // opening for the USB-C plug overmould
usb_h = 7.5;              // height above the base plate
usb_z0 = 0.0;             // opening starts at the rim (it is a notch)

/* [Screws] */
screw_d = 3.4;            // clearance hole in the base
screw_head_d = 6.2;
pilot_d = 2.7;            // self-tapping M3 into PLA/PETG
insert_holes = false;     // true: holes for M3 heat-set inserts instead
insert_d = 4.0;
boss_d = 7.5;
boss_inset = 5.2;         // boss centre -> outer wall

/* [Base] */
rear_foot_h = 8;          // height of the separate rear riser (tilt ~5 deg)
foot_d = 10;              // rubber foot recess
foot_depth = 1.0;

/* [Knob] */
knob_d = 30;
knob_h = 19;
shaft_d = 6.0;            // EC11 D-shaft
shaft_flat = 4.5;         // width across the flat
shaft_len = 20;           // shaft length from the mounting face (L = 15/20/25)
d_len = 8;                // length of the flat part at the shaft tip
knob_lift = 1.0;          // gap between knob and case top
fit = 0.15;               // printer clearance on the bore

$fn = 64;
eps = 0.01;

// ----------------------------------------------------------------------------
// Derived geometry. Key (0,0) is key 4 (front-left); +Y is towards the back.
// ----------------------------------------------------------------------------
key_x = [for (c = [0:cols-1]) c * pitch];
key_y = [for (r = [0:rows-1]) r * pitch];
enc_x = (cols - 1) * pitch + enc_gap;
enc_y = (rows - 1) * pitch / 2;

x0 = -pitch/2 - edge;
x1 = enc_x + knob_d/2 + enc_edge;
y0 = -pitch/2 - edge;
y1 = (rows - 1) * pitch + pitch/2 + edge;
W = x1 - x0;
D = y1 - y0;
H = inner_h + top_t;      // shell height

boss_xy = [
  [x0 + boss_inset, y0 + boss_inset], [x1 - boss_inset, y0 + boss_inset],
  [x0 + boss_inset, y1 - boss_inset], [x1 - boss_inset, y1 - boss_inset],
];

led_xy = [enc_x, y1 - 6.5];

module rounded_box(w, d, h, r) {
  linear_extrude(h)
    offset(r) offset(-r) square([w, d]);
}

module outline_box(h, shrink = 0) {
  translate([x0 + shrink, y0 + shrink, 0])
    rounded_box(W - 2*shrink, D - 2*shrink, h, max(corner_r - shrink, 0.5));
}

// ----------------------------------------------------------------------------
// Top shell. Built upright (top face at z = H, rim at z = 0).
// ----------------------------------------------------------------------------
module top_shell() {
  difference() {
    union() {
      difference() {
        outline_box(H);
        translate([0, 0, -eps]) outline_box(inner_h + eps, wall);
      }
      // screw bosses
      for (p = boss_xy) translate([p[0], p[1], 0]) cylinder(d = boss_d, h = H);
    }

    // switch cut-outs: through hole + underside pocket leaving plate_t
    for (x = key_x, y = key_y) translate([x, y, 0]) {
      translate([-sw_hole/2, -sw_hole/2, -eps]) cube([sw_hole, sw_hole, H + 1]);
      translate([-sw_pocket/2, -sw_pocket/2, -eps]) cube([sw_pocket, sw_pocket, H - plate_t + eps]);
    }

    // encoder
    translate([enc_x, enc_y, 0]) {
      translate([0, 0, -eps]) cylinder(d = enc_hole, h = H + 1);
      translate([-enc_pocket/2, -enc_pocket/2, -eps]) cube([enc_pocket, enc_pocket, H - enc_plate_t + eps]);
      // EC11 tab sits 7.8 mm from the shaft centre; a blind slot from below
      // keeps it from rotating. Break the tab off instead if you prefer.
      if (enc_tab)
        translate([-1.4, 7.8 - 1.0, -eps]) cube([2.8, 2.0, H - 0.6 + eps]);
    }

    // status LED
    if (led_hole > 0)
      translate([led_xy[0], led_xy[1], -eps]) cylinder(d = led_hole, h = H + 1);

    // USB-C notch in the back wall, open at the rim
    translate([board_x - usb_w/2, y1 - wall - 1, usb_z0 - eps])
      cube([usb_w, wall + 2, usb_h + eps]);

    // screw holes in the bosses (from the rim)
    for (p = boss_xy) translate([p[0], p[1], -eps])
      cylinder(d = insert_holes ? insert_d : pilot_d, h = inner_h - 1);
  }
}

// ----------------------------------------------------------------------------
// Base plate. Built with its top (inside) face at z = 0, bottom at -bot_t.
// ----------------------------------------------------------------------------
cradle_h = 2.0;
cradle_wall = 1.6;
cradle_clear = 0.4;

module base_plate() {
  difference() {
    union() {
      translate([0, 0, -bot_t]) outline_box(bot_t);

      // board cradle: three low walls, open towards the USB notch
      bw = board_w + 2*cradle_clear;
      bl = board_l + cradle_clear;
      by1 = y1 - wall;                 // board's back edge touches the wall
      translate([board_x - bw/2 - cradle_wall, by1 - bl - cradle_wall, 0])
        difference() {
          cube([bw + 2*cradle_wall, bl + cradle_wall, cradle_h]);
          translate([cradle_wall, cradle_wall, -eps]) cube([bw, bl + 1, cradle_h + 1]);
        }

    }

    // countersunk screw holes
    for (p = boss_xy) translate([p[0], p[1], 0]) {
      translate([0, 0, -bot_t - 1]) cylinder(d = screw_d, h = bot_t + 2);
      translate([0, 0, -bot_t - eps]) cylinder(d1 = screw_head_d, d2 = screw_d, h = (screw_head_d - screw_d)/2);
    }

    // rubber foot recesses at the front (the rear ones are on the riser)
    for (x = [x0 + 14, x1 - 14])
      translate([x, y0 + 12, -bot_t - eps]) cylinder(d = foot_d, h = foot_depth);
  }
}

// ----------------------------------------------------------------------------
// Rear riser: tilts the deck towards you. It is held by the two rear screws
// (use M3x12 there instead of M3x8). Built with its top at z = 0.
// ----------------------------------------------------------------------------
riser_d = 12;

module riser() {
  rear = [for (p = boss_xy) if (p[1] > (y0 + y1) / 2) p];
  difference() {
    translate([x0 + 1, y1 - riser_d - 0.5, -rear_foot_h])
      rounded_box(W - 2, riser_d, rear_foot_h, 3);
    for (p = rear) translate([p[0], p[1], 0]) {
      translate([0, 0, -rear_foot_h - 1]) cylinder(d = screw_d, h = rear_foot_h + 2);
      // counterbore from below, leaving 3 mm for the screw to clamp
      translate([0, 0, -rear_foot_h - eps]) cylinder(d = screw_head_d + 0.6, h = rear_foot_h - 3);
    }
    for (x = [x0 + 16, x1 - 16])
      translate([x, y1 - riser_d/2 - 0.5, -rear_foot_h - eps]) cylinder(d = foot_d, h = foot_depth);
  }
}

// ----------------------------------------------------------------------------
// Knob. Built upright (bottom at z = 0).
// ----------------------------------------------------------------------------
module knob() {
  recess_d = 13;
  recess_h = 4;
  bore_top = shaft_len - enc_plate_t - knob_lift;  // shaft tip, from knob bottom
  ridges = 24;
  bore_d = shaft_d + 2*fit;
  difference() {
    union() {
      cylinder(d = knob_d - 2, h = knob_h, $fn = 96);
      for (i = [0:ridges-1]) rotate(i * 360 / ridges)
        translate([knob_d/2 - 1, 0, 0]) cylinder(d = 2, h = knob_h, $fn = 16);
    }
    // underside recess for the nut and bushing
    translate([0, 0, -eps]) cylinder(d = recess_d, h = recess_h + eps);
    // shaft bore: round where the shaft is round...
    translate([0, 0, -eps]) cylinder(d = bore_d, h = bore_top - d_len + eps);
    // ...and D-shaped over the last d_len mm, where the shaft has its flat
    translate([0, 0, bore_top - d_len]) linear_extrude(d_len + 0.3)
      intersection() {
        circle(d = bore_d);
        translate([-bore_d, -bore_d/2]) square([2*bore_d, shaft_flat + 2*fit]);
      }
    // indicator line on top
    translate([-0.8, knob_d/2 - 8, knob_h - 0.6]) cube([1.6, 6, 1]);
  }
}

// ----------------------------------------------------------------------------
// Keycap / switch stand-ins for the assembly preview
// ----------------------------------------------------------------------------
module preview_parts() {
  for (x = key_x, y = key_y) translate([x, y, bot_t + H]) {
    color("dimgray") translate([-7, -7, -5]) cube([14, 14, 11.6 - 5]);
    color("whitesmoke") translate([-9, -9, 6.6]) rounded_box(18, 18, 8, 2);
  }
  color("orange") translate([enc_x, enc_y, bot_t + H + knob_lift]) knob();
  color("teal") translate([board_x - board_w/2, y1 - wall - board_l, bot_t + 0.1]) cube([board_w, board_l, 1.2]);
}

// ----------------------------------------------------------------------------
if (part == "top") {
  // upside down for printing
  translate([0, 0, H]) rotate([180, 0, 0]) top_shell();
} else if (part == "bottom") {
  translate([0, 0, bot_t]) base_plate();
} else if (part == "riser") {
  translate([0, 0, rear_foot_h]) riser();
} else if (part == "knob") {
  translate([0, 0, knob_h]) rotate([180, 0, 0]) knob();
} else {
  tilt = atan(rear_foot_h / (D - riser_d / 2));
  translate([0, y0, 0]) rotate([tilt, 0, 0]) translate([0, -y0, bot_t]) {
    color("lightsteelblue") base_plate();
    color("slategray") translate([0, 0, -bot_t]) riser();
    color("steelblue", 0.9) top_shell();
    translate([0, 0, -bot_t]) preview_parts();
  }
}
