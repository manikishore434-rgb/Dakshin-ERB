import unittest
from decimal import Decimal

from app import units, util
from app.services.sales import compute_line_tax


class TaxTest(unittest.TestCase):
    def test_intra_state_splits_in_half(self):
        self.assertEqual(compute_line_tax(750000, 500, True), (18750, 18750, 0))

    def test_inter_state_igst(self):
        self.assertEqual(compute_line_tax(600000, 500, False), (0, 0, 30000))

    def test_half_up_rounding_never_drifts_by_float(self):
        # 3 packets x Rs 0.35 = 105 paise taxable; 2.5% = 2.625 paise -> 3 paise each (half-up, not banker's)
        self.assertEqual(compute_line_tax(105, 500, True), (3, 3, 0))
        self.assertEqual(util.round_half_up(Decimal("0.5")), 1)
        self.assertEqual(util.round_half_up(Decimal("2.5")), 3)

    def test_money_arithmetic_is_exact(self):
        self.assertEqual(util.to_paise("0.1") + util.to_paise("0.2"), util.to_paise("0.3"))


class UnitTest(unittest.TestCase):
    flour = {"name": "Flour", "kind": "raw", "base_unit": "kg", "carton_size": None}
    murukku = {"name": "Murukku", "kind": "finished", "base_unit": "packet", "carton_size": 20}

    def test_grams_to_kg(self):
        self.assertEqual(units.to_base_milli(2500, "g", self.flour), 2500)   # 2.5 kg
        self.assertEqual(units.to_base_milli("1.2", "kg", self.flour), 1200)

    def test_cartons_to_packets(self):
        self.assertEqual(units.to_base_milli(3, "carton", self.murukku), 60000)  # 60 packets

    def test_incompatible_unit_rejected(self):
        with self.assertRaises(util.ServiceError):
            units.to_base_milli(1, "l", self.flour)

    def test_variance_tolerance_is_strict(self):
        self.assertFalse(util.beyond_tolerance(200, 194, 300))   # exactly -3% is not beyond 3%
        self.assertTrue(util.beyond_tolerance(200, 188, 300))    # -6%
        self.assertTrue(util.beyond_tolerance(10000, 10500, 300))


if __name__ == "__main__":
    unittest.main()
