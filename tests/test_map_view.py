import unittest

import folium
from folium.plugins import MarkerCluster

from lib import map_view
from lib.rooms_data import load_rooms, visible_rooms

CENTERS = {"학교": (37.4505, 129.1615), "정문": (37.4502, 129.1625), "후문": (37.455, 129.1668)}


class AttachCoordsTest(unittest.TestCase):
    def test_uses_coords_by_name_and_dong(self):
        rooms = [{"id": "r1", "name": "가", "dong": "교동", "area": "정문"}]
        coords = {("가", "교동"): {"lat": 37.451, "lon": 129.163, "precision": "도로중심"}}
        out = map_view.attach_coords(rooms, coords, CENTERS)
        self.assertEqual((out[0]["lat"], out[0]["lon"], out[0]["geo_precision"]), (37.451, 129.163, "도로중심"))

    def test_falls_back_to_area_then_school(self):
        rooms = [
            {"id": "r1", "name": "가", "dong": "?", "area": "후문"},
            {"id": "r2", "name": "나", "dong": "?", "area": "없는곳"},
        ]
        out = map_view.attach_coords(rooms, {}, CENTERS)
        self.assertEqual((out[0]["lat"], out[0]["lon"]), CENTERS["후문"])
        self.assertEqual(out[0]["geo_precision"], "생활권중심")
        self.assertEqual((out[1]["lat"], out[1]["lon"]), CENTERS["학교"])

    def test_overlapping_points_are_spread_deterministically_and_stay_close(self):
        rooms = [{"id": f"r{i}", "name": "?", "dong": "?", "area": "정문"} for i in range(5)]
        a = map_view.attach_coords(rooms, {}, CENTERS)
        b = map_view.attach_coords(rooms, {}, CENTERS)
        self.assertEqual([(r["lat"], r["lon"]) for r in a], [(r["lat"], r["lon"]) for r in b])
        self.assertEqual(len({(r["lat"], r["lon"]) for r in a}), 5)
        for r in a:
            self.assertLess(abs(r["lat"] - CENTERS["정문"][0]), 0.0005)
            self.assertLess(abs(r["lon"] - CENTERS["정문"][1]), 0.0005)

    def test_single_point_is_not_moved(self):
        out = map_view.attach_coords([{"id": "r1", "name": "?", "dong": "?", "area": "정문"}], {}, CENTERS)
        self.assertEqual((out[0]["lat"], out[0]["lon"]), CENTERS["정문"])


class LabelTest(unittest.TestCase):
    def test_price_label(self):
        self.assertEqual(map_view.price_label({"monthly": 30.0}), "30")
        self.assertEqual(map_view.price_label({"monthly": 27.5}), "27.5")
        self.assertEqual(map_view.price_label({"monthly": None}), "?")

    def test_tooltip_round_trip(self):
        room = {"id": "r012", "name": "후문 원룸 [신축]", "monthly": 35.0}
        self.assertEqual(map_view.clicked_room_id(map_view.tooltip_text(room)), "r012")
        self.assertIsNone(map_view.clicked_room_id(None))
        self.assertIsNone(map_view.clicked_room_id("강원대 삼척캠퍼스"))

    def test_price_tone(self):
        medians = {"정문": {"median": 35.0, "count": 5}}
        self.assertEqual(map_view.price_tone({"monthly": 30.0, "area": "정문"}, medians), "cheap")
        self.assertEqual(map_view.price_tone({"monthly": 40.0, "area": "정문"}, medians), "pricey")
        self.assertEqual(map_view.price_tone({"monthly": 36.0, "area": "정문"}, medians), "neutral")
        self.assertEqual(map_view.price_tone({"monthly": None, "area": "정문"}, medians), "neutral")


class RealDataTest(unittest.TestCase):
    def test_every_visible_room_gets_a_point_on_the_map(self):
        rooms = visible_rooms(load_rooms() or [])
        self.assertGreater(len(rooms), 0)
        centers = map_view.load_centers()
        self.assertIn("학교", centers)
        placed = map_view.attach_coords(rooms, map_view.load_coords(), centers)
        self.assertEqual(len(placed), len(rooms))
        fmap = map_view.build_map(placed, {}, centers)
        layers = [fmap] + [c for c in fmap._children.values() if isinstance(c, MarkerCluster)]
        markers = [c for layer in layers for c in layer._children.values() if isinstance(c, folium.Marker)]
        self.assertEqual(len(markers), len(placed) + len(centers))


if __name__ == "__main__":
    unittest.main()
