// Icon keycaps for the stream deck: Discord full mute (deafen) and Print Screen.
//
// Based on the emoji keycap generator by Benoit Perocheau
// (Designed by Benoit Perocheau,
//  License: CC-Attribution-Noncommercial-Share Alike).
// This file is a derivative and keeps that license (CC BY-NC-SA), not the
// MIT license of the rest of the repository.
//
// Changes from the original:
//  - the keycap is one module instead of nine copied blocks
//  - the emoji text is replaced by icons drawn as geometry, because emoji
//    fonts have neither a Discord deafen icon nor a screenshot icon
//  - choose which part to export, so the icon can be printed in a second
//    colour (inlay) or simply engraved for a single-colour print
//
// The keycap is printed top-down: the top face lies on the bed and the icon
// is mirrored so it reads correctly when the cap is turned over.
//
// Export from the command line, for example:
//   openscad -D 'Icon="deafen"' -D 'Part="body"' -o deafen_body.stl icon_keycaps.scad
//   openscad -D 'Icon="deafen"' -D 'Part="icon"' -o deafen_icon.stl icon_keycaps.scad

/* [Keycap] */
// Which icon: "deafen" (Discord full mute), "printscreen", or "both" side by side
Icon = "both"; // [both, deafen, printscreen]
// "inlay": icon in a second colour, flush with the top. "engrave": icon cut
// into the top, one colour.
Style = "inlay"; // [inlay, engrave]
// "all" for a preview; export "body" and "icon" separately for a two-colour print
Part = "all"; // [all, body, icon]
//DSA=7mm; XDA=9mm
Keycap_Height = 7.5;
// Width of the icon on the 14 mm top face
Icon_Size = 11;
// Inlay thickness (use a multiple of your layer height)
Icon_Depth = 0.4;
// Engrave depth
Engrave_Depth = 0.6;

/* [Colors] */
Keycap_Color = "#ffffff";
Icon_Color = "#d83c3e";

// ---------------------------------------------------------------------------
// Keycap shape (from the original generator)
// ---------------------------------------------------------------------------
module rounded_outline(size, corner) {
  // square with quarter-circle corners cut in, as in the original
  difference() {
    square(size, center = true);
    for (sx = [-1, 1], sy = [-1, 1])
      translate([sx * (size / 2 - corner), sy * (size / 2 - corner)])
        difference() {
          translate([sx * corner / 2, sy * corner / 2]) square(corner, center = true);
          circle(r = corner, $fn = 50);
        }
  }
}

module keycap_body() {
  union() {
    difference() {
      // outside: 14 mm top growing to 18 mm at the skirt
      linear_extrude(height = Keycap_Height, center = false, scale = 1.286)
        rounded_outline(14, 2);
      // hollow inside, 1 mm top thickness
      translate([0, 0, 1])
        linear_extrude(height = Keycap_Height, center = false, scale = 1.286)
          rounded_outline(12, 1);
    }
    // MX stem socket
    linear_extrude(height = Keycap_Height - 1, center = false)
      difference() {
        circle(d = 5.5, $fn = 50);
        square([1.25, 4.25], center = true);
        square([4.25, 1.25], center = true);
      }
  }
}

// ---------------------------------------------------------------------------
// Icons, drawn on a 24 x 24 grid (2-unit strokes) and scaled to Icon_Size.
// ---------------------------------------------------------------------------
// Removes slivers thinner than 2*d that cut-outs can leave behind (they are
// too thin to print); full 2-unit strokes are kept.
module drop_slivers(d = 0.6) {
  offset(r = d, $fn = 24) offset(r = -d, $fn = 24) children();
}

module stroke_line(a, b, w) {
  hull() {
    translate(a) circle(d = w, $fn = 24);
    translate(b) circle(d = w, $fn = 24);
  }
}

module rounded_rect(x0, y0, x1, y1, r) {
  translate([x0 + r, y0 + r]) offset(r = r, $fn = 32) square([x1 - x0 - 2 * r, y1 - y0 - 2 * r]);
}

// Discord "deafen": headphones with a slash from bottom left to top right.
module icon_deafen() {
  slash_a = [3.2, 2.2];
  slash_b = [21.2, 21.6];
  slash_y = function(x) slash_a[1] + (x - slash_a[0]) * (slash_b[1] - slash_a[1]) / (slash_b[0] - slash_a[0]);
  drop_slivers() difference() {
    union() {
      // headband: upper part of a ring
      intersection() {
        translate([12, 11]) difference() {
          circle(r = 9.2, $fn = 96);
          circle(r = 7.2, $fn = 96);
        }
        translate([0, 9]) square([24, 15]);
      }
      // ear cups
      rounded_rect(2.8, 2.5, 8.6, 11.5, 2);
      rounded_rect(15.4, 2.5, 21.2, 11.5, 2);
    }
    // gap around the slash
    stroke_line(slash_a, slash_b, 5.2);
    // the part of the left ear cup below the slash goes, as in Discord's icon
    polygon([[-1, -1], [12, -1], [12, slash_y(12)], [-1, slash_y(-1)]]);
  }
  stroke_line(slash_a, slash_b, 2);
}

// Print Screen: dashed frame with a camera in the lower right corner.
module camera_outline() {
  difference() {
    camera_fill();
    offset(delta = -2) camera_fill();
  }
  // lens ring
  translate([15.2, 6.6]) difference() {
    circle(r = 3, $fn = 64);
    circle(r = 1.1, $fn = 48);
  }
}

module camera_fill() {
  union() {
    rounded_rect(8.6, 1.8, 22, 12.6, 2.2);
    // viewfinder bump on top
    polygon([[11.4, 12], [13.6, 15.2], [17, 15.2], [19.2, 12]]);
  }
}

module icon_printscreen() {
  // frame: rounded square stroke, kept only at the corners and two dashes
  // per side, and cut away around the camera
  drop_slivers() difference() {
    intersection() {
      difference() {
        rounded_rect(2, 2, 22, 22, 4);
        rounded_rect(4, 4, 20, 20, 2);
      }
      union() {
        for (x = [0, 17.5], y = [0, 17.5]) translate([x, y]) square(6.5);
        for (p = [8.6, 13.4]) {
          translate([p, 0]) square([2.4, 24]);  // dashes on top and bottom
          translate([0, p]) square([24, 2.4]);  // dashes on left and right
        }
      }
    }
    offset(r = 1.6) camera_fill();
  }
  camera_outline();
}

module icon_2d(name) {
  s = Icon_Size / 24;
  // centred on the keycap, mirrored because the cap prints top-down
  mirror([1, 0, 0]) scale([s, s]) translate([-12, -12]) {
    if (name == "deafen") icon_deafen();
    else if (name == "printscreen") icon_printscreen();
  }
}

// ---------------------------------------------------------------------------
// One finished keycap
// ---------------------------------------------------------------------------
module icon_keycap(name) {
  depth = Style == "inlay" ? Icon_Depth : Engrave_Depth;
  if (Part == "all" || Part == "body")
    color(Keycap_Color) difference() {
      keycap_body();
      translate([0, 0, -0.2]) linear_extrude(depth + 0.2) icon_2d(name);
    }
  if (Style == "inlay" && (Part == "all" || Part == "icon"))
    color(Icon_Color) linear_extrude(depth) icon_2d(name);
}

if (Icon == "both") {
  icon_keycap("deafen");
  translate([20, 0, 0]) icon_keycap("printscreen");
} else {
  icon_keycap(Icon);
}
