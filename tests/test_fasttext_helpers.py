import unittest

from app import (
    fallback_pashto_prediction,
    parse_hf_prediction_output,
    normalize_hf_prediction_label,
)


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

    def test_fallback_pashto_prediction(self):
        self.assertEqual(fallback_pashto_prediction("da khabar sta khapare"), "pashto")
        self.assertEqual(fallback_pashto_prediction("this is a normal english sentence"), "not_pashto")


if __name__ == "__main__":
    unittest.main()
