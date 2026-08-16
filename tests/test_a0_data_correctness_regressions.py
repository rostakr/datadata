from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyzazprav.normalization.staging import canonical_direction, iso_utc_to_unix_us
from analyzazprav.a5_ai.integration_a2 import A2SQLiteMessageSource


class DataCorrectnessRegressionTests(unittest.TestCase):
    def test_unknown_direction_is_not_collapsed_to_incoming(self):
        self.assertEqual(canonical_direction(None), "unknown")
        self.assertEqual(canonical_direction(object()), "unknown")
        self.assertEqual(canonical_direction(True), "outgoing")
        self.assertEqual(canonical_direction(1), "outgoing")
        self.assertEqual(canonical_direction(False), "incoming")
        self.assertEqual(canonical_direction(0), "incoming")

    def test_a2_utc_microseconds_are_exact_without_float(self):
        self.assertEqual(iso_utc_to_unix_us("2500-01-01T00:00:00.123457Z"), 16_725_225_600_123_457)
        self.assertEqual(iso_utc_to_unix_us("1969-12-31T23:59:59.999999Z"), -1)

    def test_a5_utc_microseconds_round_trip_exactly(self):
        value = datetime(2500, 1, 1, 0, 0, 0, 123457, tzinfo=timezone.utc)
        exact = A2SQLiteMessageSource._to_utc_us(value)
        self.assertEqual(exact, 16_725_225_600_123_457)
        self.assertEqual(A2SQLiteMessageSource._from_utc_us(exact), value)
        self.assertEqual(A2SQLiteMessageSource._to_utc_us(datetime(1969, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)), -1)


if __name__ == "__main__":
    unittest.main()
