import unittest

from grbr_explain.min_gerber_parser import GrbrCoordSys

class TestModuleDemo(unittest.TestCase):
    def test_gerber_coordinate_system_parse_coord(self):
        gcs = GrbrCoordSys(4, 6)
        val = gcs.parse_grbr_coord("123456000")
        self.assertEqual(val, 123.456)
