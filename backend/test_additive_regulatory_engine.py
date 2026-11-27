import unittest
from unittest.mock import patch

import additive_regulatory_engine
from additive_regulatory_engine import assess_additives


class AdditiveRegulatoryEngineTests(unittest.TestCase):
    def test_category_specific_limit_is_traceable(self):
        result = assess_additives({
            "additives_tags": ["en:E407"],
            "category": "Condensed milk products",
        })
        additive = result["additives"][0]
        self.assertEqual(result["overall_status"], "permitted_with_conditions")
        self.assertEqual(additive["max_level"]["value"], 150)
        self.assertEqual(additive["max_level"]["basis"], "final product")
        self.assertEqual(additive["reference"]["section"], "Table 1, FC 1.3.1")
        self.assertIn("thickener", additive["functional_class"])
        self.assertEqual(result["compliance_status"], "compliance_not_verified")

    def test_missing_concentration_never_claims_compliance(self):
        result = assess_additives({
            "additives_tags": ["E330"],
            "category": "Fruit nectar concentrates",
            "ingredients_text": "citric acid",
        })
        self.assertEqual(result["compliance_status"], "compliance_not_verified")
        self.assertEqual(result["additives"][0]["max_level"]["value"], 5000)

    def test_matching_concentration_can_be_compared(self):
        payload = {
            "additives_tags": ["E407"],
            "category": "Sweetened condensed milk",
        }
        compliant = assess_additives({
            **payload,
            "additive_concentrations": {"E407": {"mg_per_kg": 100, "basis": "final product"}},
        })
        non_compliant = assess_additives({
            **payload,
            "additive_concentrations": {"E407": {"mg_per_kg": 200, "basis": "final product"}},
        })
        self.assertEqual(compliant["compliance_status"], "compliant")
        self.assertEqual(non_compliant["compliance_status"], "non_compliant")

    def test_mismatched_basis_is_not_compared(self):
        result = assess_additives({
            "additives_tags": ["E223"],
            "category": "White sugar",
            "additive_concentrations": {"E223": {"mg_per_kg": 10, "basis": "compound mass"}},
        })
        self.assertEqual(result["compliance_status"], "compliance_not_verified")
        self.assertTrue(any("does not match" in warning for warning in result["warnings"]))

    def test_conditional_additive_without_category_is_unverifiable(self):
        result = assess_additives({"additives_tags": ["E320"], "category": None})
        self.assertEqual(result["overall_status"], "insufficient_information")
        self.assertEqual(result["additives"][0]["permission_status"], "unable_to_verify")

    def test_unverified_e306_is_not_declared_permitted(self):
        result = assess_additives({"additives_tags": ["E306"], "category": "Fat spreads"})
        self.assertEqual(result["additives"][0]["permission_status"], "unable_to_verify")
        self.assertTrue(any("INS 306" in note for note in result["additives"][0]["limitations"]))

    def test_unknown_additive_is_explicit(self):
        result = assess_additives({"additives_tags": ["E999"], "category": "Beverages"})
        self.assertEqual(result["overall_status"], "insufficient_information")
        self.assertEqual(result["additives"][0]["permission_status"], "unable_to_verify")

    def test_synonym_and_ins_matching(self):
        result = assess_additives({
            "ingredients_text": "noodles with monosodium glutamate",
            "category": "Instant noodles",
        })
        additive = result["additives"][0]
        self.assertEqual(additive["identified_as"], "E621")
        self.assertIn("ingredient_name", additive["detected_via"])
        self.assertTrue(any("Note 256" in condition for condition in additive["conditions"]))

    def test_unavailable_additive_data_does_not_infer_absence(self):
        result = assess_additives({"additives_available": False})
        self.assertEqual(result["overall_status"], "insufficient_information")
        self.assertTrue(any("absence" in warning for warning in result["warnings"]))

    def test_regulatory_references_are_always_traceable(self):
        result = assess_additives({"additives_tags": ["E500"], "category": "Bread"})
        self.assertTrue(result["regulatory_references"])
        self.assertTrue(all(ref["document"] for ref in result["regulatory_references"]))
        self.assertEqual(result["additives"][0]["permission_status"], "permitted_gmp")

    def test_verified_restricted_record_is_reported_as_restricted(self):
        restricted = {
            "name": "Test restricted additive",
            "ins": ["999"],
            "synonyms": [],
            "functional_class": ["preservative"],
            "permission": "restricted",
            "references": ["COMP-A-v3"],
            "notes": ["Test-only record."],
            "category_rules": [],
        }
        with patch.dict(additive_regulatory_engine.ADDITIVES, {"E999": restricted}):
            result = assess_additives({"additives_tags": ["E999"], "category": "Bread"})
        self.assertEqual(result["overall_status"], "restricted_or_not_permitted")
        self.assertEqual(result["additives"][0]["permission_status"], "restricted_or_not_permitted")


if __name__ == "__main__":
    unittest.main()
