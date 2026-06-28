import unittest

import numpy as np

from hub_core.ispd_physics import calculate_trap_density, fit_ispd_data, fit_ispd_data_with_offset


class IspdPhysicsTest(unittest.TestCase):
    def test_calculate_trap_density_fails_explicitly_without_validated_model(self):
        with self.assertRaisesRegex(NotImplementedError, "project-specific"):
            calculate_trap_density(1.0, 10.0, 100.0, 3.0)

    def test_calculate_trap_density_array_inputs_do_not_return_none_silently(self):
        with self.assertRaisesRegex(NotImplementedError, "validated"):
            calculate_trap_density(np.array([1.0, 2.0]), np.array([10.0, 20.0]), 100.0, 3.0)

    def test_fit_return_shapes_remain_stable(self):
        t = np.linspace(0, 10, 40)
        v = 2.0 * np.exp(-t / 2.0) + 5.0 * np.exp(-t / 8.0)

        popt, perr, r2 = fit_ispd_data(t, v)
        self.assertEqual(len(popt), 4)
        self.assertEqual(len(perr), 4)
        self.assertIsInstance(float(r2), float)

        popt_offset, perr_offset, r2_offset = fit_ispd_data_with_offset(t, v)
        self.assertEqual(len(popt_offset), 5)
        self.assertEqual(len(perr_offset), 5)
        self.assertIsInstance(float(r2_offset), float)


if __name__ == "__main__":
    unittest.main()
