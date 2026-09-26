import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.fetch_public_data import to_yolo_bbox


def test_bbox_passthrough():
    row = to_yolo_bbox(2, [0.5, 0.5, 0.2, 0.4])
    assert row == "2 0.500000 0.500000 0.200000 0.400000"


def test_polygon_collapses_to_enclosing_box():
    # a unit square polygon (0,0)-(1,0)-(1,1)-(0,1) must collapse to the
    # same box a bbox annotation of that square would have produced
    coords = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    row = to_yolo_bbox(0, coords)
    assert row == "0 0.500000 0.500000 1.000000 1.000000"


def test_polygon_off_center():
    # triangle (0.2,0.3) (0.6,0.3) (0.4,0.7) -> enclosing box
    # x: 0.2..0.6 -> xc 0.4, w 0.4 | y: 0.3..0.7 -> yc 0.5, h 0.4
    coords = [0.2, 0.3, 0.6, 0.3, 0.4, 0.7]
    row = to_yolo_bbox(1, coords)
    assert row == "1 0.400000 0.500000 0.400000 0.400000"
