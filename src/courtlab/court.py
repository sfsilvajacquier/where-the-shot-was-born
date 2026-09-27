"""The FIBA court, in feet, in the frame of reference of SkillCorner's events: origin at the centre, attacked hoop at negative x."""

from __future__ import annotations

M = 3.28084  # feet in a metre

LENGTH, WIDTH = 28.0 * M, 15.0 * M
HOOP_X = -(14.0 - 1.575) * M  # ring centre 1.575 m from the baseline: -40.76 ft (the shots' own `distance` field says -40.75)
HOOP = (HOOP_X, 0.0)
THREE_RADIUS = 6.75 * M       # arc, measured from the ring centre
THREE_CORNER_Y = (7.5 - 0.9) * M  # the straight corner lines run 0.90 m inside the sidelines
PAINT_LENGTH, PAINT_WIDTH = 5.8 * M, 4.9 * M
FREE_THROW_RADIUS = 1.8 * M
NO_CHARGE_RADIUS = 1.25 * M
BACKBOARD_X = -(14.0 - 1.2) * M
RIM_HEIGHT = 3.05 * M


def as_dict() -> dict:
    return {"units": "ft", "length": round(LENGTH, 2), "width": round(WIDTH, 2), "hoop": [round(HOOP_X, 2), 0.0],
            "three_radius": round(THREE_RADIUS, 2), "three_corner_y": round(THREE_CORNER_Y, 2),
            "paint": [round(PAINT_LENGTH, 2), round(PAINT_WIDTH, 2)], "free_throw_radius": round(FREE_THROW_RADIUS, 2),
            "no_charge_radius": round(NO_CHARGE_RADIUS, 2), "backboard_x": round(BACKBOARD_X, 2), "rim_height": round(RIM_HEIGHT, 2)}
