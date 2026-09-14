import unittest

from app import parse_hf_prediction_output, normalize_hf_prediction_label


class TestHFDetectorHelpers(unittest.TestCase):
    def test_normalize_hf_prediction_label(self):
        self.assertEqual(normalize_hf_prediction_label("pashto"), "pashto")
        self.assertEqual(normalize_hf_prediction_label("not_pashto"), "not_pashto")
        self.assertEqual(normalize_hf_prediction_label("PASHTO"), "pashto")

    def test_parse_hf_prediction_output(self):
        result = parse_hf_prediction_output(["pashto", 0.97])
        self.assertEqual(result[0], "pashto")
        self.assertAlmostEqual(result[1], 0.97)

        with self.assertRaises(ValueError):
            parse_hf_prediction_output({"error": "ZeroGPU quota exceeded"})


if __name__ == "__main__":
    unittest.main()
