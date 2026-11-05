import unittest

from tools import geocode_juso as g


class ProjectionTest(unittest.TestCase):
    def test_origin_maps_to_false_origin(self):
        x, y = g.wgs84_to_utmk(38.0, 127.5)
        self.assertAlmostEqual(x, 1_000_000.0, places=3)
        self.assertAlmostEqual(y, 2_000_000.0, places=3)
        lat, lon = g.utmk_to_wgs84(1_000_000.0, 2_000_000.0)
        self.assertAlmostEqual(lat, 38.0, places=9)
        self.assertAlmostEqual(lon, 127.5, places=9)

    def test_round_trip_in_samcheok_is_under_a_centimeter(self):
        for lat, lon in [(37.4505, 129.1615), (37.4470, 129.1668), (37.4250, 129.1350), (37.4680, 129.1950)]:
            x, y = g.wgs84_to_utmk(lat, lon)
            self.assertGreater(x, 1_000_000)
            self.assertLess(y, 2_000_000)
            back = g.utmk_to_wgs84(x, y)
            self.assertLess(g.gap_m(lat, lon, *back), 0.01)

    def test_gap_m_one_thousandth_degree_latitude(self):
        self.assertAlmostEqual(g.gap_m(37.0, 129.0, 37.001, 129.0), 111.2, delta=0.5)


class PickTest(unittest.TestCase):
    ITEM = {"roadAddrPart1": "강원특별자치도 삼척시 중앙로 269", "admCd": "5123010100", "rnMgtSn": "512303000001",
            "udrtYn": "0", "buldMnnm": "269", "buldSlno": "0"}

    def test_exact_match_ignores_spaces_and_old_province_name(self):
        self.assertIs(g.pick("강원도 삼척시 중앙로269", [self.ITEM]), self.ITEM)

    def test_same_address_with_several_buildings_takes_first(self):
        twin = dict(self.ITEM, bdNm="2동")
        self.assertIs(g.pick("강원특별자치도 삼척시 중앙로 269", [self.ITEM, twin]), self.ITEM)

    def test_no_exact_match_returns_none(self):
        other = dict(self.ITEM, roadAddrPart1="강원특별자치도 삼척시 중앙로 271", buldMnnm="271")
        self.assertIsNone(g.pick("강원특별자치도 삼척시 중앙로 269", [other]))
        self.assertIsNone(g.pick("강원특별자치도 삼척시 중앙로 269", []))


if __name__ == "__main__":
    unittest.main()
