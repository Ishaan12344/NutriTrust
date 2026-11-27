"""Pure tests for tracker item normalization and period aggregation."""

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tracker_service import (
    build_item_document,
    build_snapshot,
    daily_targets,
    delete_tracker_item,
    period_range,
)


def item(name, status, nutrition, day="2026-11-27", **extra):
    return {
        "item_id": name,
        "name": name,
        "status": status,
        "local_date": day,
        "nutrition": nutrition,
        "partial_data": False,
        "allergens": [],
        **extra,
    }


class TrackerItemTests(unittest.TestCase):
    def test_missing_name_and_partial_nutrition_are_flagged(self):
        doc = build_item_document(
            {
                "username": "Asha",
                "date": "2026-11-27",
                "nutrition": {"energy_kcal": 120, "protein": 4},
                "nutrition_basis": "per_serving",
            }
        )
        self.assertEqual(doc["name"], "Unnamed product")
        self.assertTrue(doc["needs_name"])
        self.assertEqual(doc["status"], "pending")
        self.assertTrue(doc["partial_data"])
        self.assertEqual(doc["missing_fields"], ["total_carbohydrate", "total_fat"])
        self.assertFalse(doc["manual_name"])

    def test_manual_name_is_marked_as_user_supplied(self):
        doc = build_item_document(
            {
                "name": "Homemade burger",
                "source": "manual_name",
                "nutrition": {
                    "energy_kcal": 400,
                    "protein": 20,
                    "total_carbohydrate": 40,
                    "total_fat": 18,
                },
            }
        )
        self.assertTrue(doc["manual_name"])
        self.assertFalse(doc["needs_name"])
        self.assertFalse(doc["partial_data"])


class TrackerSnapshotTests(unittest.TestCase):
    def test_only_eaten_items_count_and_counts_are_complete(self):
        items = [
            item("Oats", "eaten", {"energy_kcal": 300, "protein": 10, "fiber": 4, "sodium": 100}),
            item("Chips", "not_eaten", {"energy_kcal": 500, "sodium": 900}),
            item("Dal", "eaten", {"energy_kcal": 250, "protein": 12, "fiber": 6, "sodium": 200}),
            item("Bar", "pending", {"energy_kcal": 200}),
        ]
        snapshot = build_snapshot(items, {"gender": "female", "weight": 60}, "daily", date(2026, 11, 27))

        self.assertEqual(snapshot["totals"]["energy_kcal"], 550)
        self.assertEqual(snapshot["totals"]["protein"], 22)
        self.assertEqual(snapshot["counts"], {"eaten": 2, "not_eaten": 1, "pending": 1})
        self.assertEqual(len(snapshot["items"]), 4)
        self.assertTrue(snapshot["has_data"])
        self.assertEqual(snapshot["range"]["days"], 1)

    def test_low_fibre_and_high_sodium_produce_actionable_suggestions(self):
        items = [
            item(
                "Salty snack",
                "eaten",
                {"energy_kcal": 900, "protein": 10, "fiber": 1, "sodium": 3000, "sugar": 10},
            )
        ]
        snapshot = build_snapshot(items, {}, "daily", date(2026, 11, 27))
        titles = [rec["title"] for rec in snapshot["recommendations"]]
        self.assertIn("Go easy on salt", titles)
        self.assertIn("Add a fibre source", titles)
        self.assertTrue(all(rec["message"] for rec in snapshot["recommendations"]))

    def test_weekly_targets_scale_with_the_period(self):
        snapshot = build_snapshot([], {}, "weekly", date(2026, 11, 27))
        self.assertEqual(snapshot["range"]["days"], 7)
        self.assertAlmostEqual(
            snapshot["period_targets"]["protein"],
            snapshot["targets"]["protein"] * 7,
        )
        self.assertFalse(snapshot["has_data"])
        self.assertEqual(snapshot["highlight"], "No intake marked this week yet.")


class PeriodAndTargetTests(unittest.TestCase):
    def test_period_ranges(self):
        self.assertEqual(period_range("daily", date(2026, 11, 27)), (date(2026, 11, 27), date(2026, 11, 27)))
        self.assertEqual(period_range("weekly", date(2026, 11, 27)), (date(2026, 11, 23), date(2026, 11, 29)))
        self.assertEqual(period_range("monthly", date(2026, 11, 27)), (date(2026, 11, 1), date(2026, 11, 30)))

    def test_profile_changes_iron_and_protein_targets(self):
        targets = daily_targets({"gender": "female", "weight": 70})
        self.assertEqual(targets["iron"], 18.0)
        self.assertEqual(targets["protein"], 56.0)
        male = daily_targets({"gender": "male", "weight": 70})
        self.assertEqual(male["iron"], 8.0)


class TrackerDeletionTests(unittest.TestCase):
    def test_delete_removes_database_and_local_copies(self):
        collection = Mock()
        collection.delete_one.return_value = SimpleNamespace(deleted_count=1)
        local_items = [
            {"item_id": "item-1", "username": "pushkar"},
            {"item_id": "other-user-item", "username": "someone-else"},
        ]

        with (
            patch("tracker_service.get_db", return_value={"tracker_items": collection}),
            patch("tracker_service._read_local", return_value=local_items),
            patch("tracker_service._write_local") as write_local,
        ):
            delete_tracker_item("item-1", "PUSHKAR")

        collection.delete_one.assert_called_once_with(
            {"item_id": "item-1", "username": "pushkar"}
        )
        write_local.assert_called_once_with([local_items[1]])

    def test_delete_falls_back_to_matching_local_item(self):
        local_items = [
            {"item_id": "item-1", "username": "pushkar"},
            {"item_id": "other-user-item", "username": "someone-else"},
        ]

        with (
            patch("tracker_service.get_db", side_effect=RuntimeError("offline")),
            patch("tracker_service._read_local", return_value=local_items),
            patch("tracker_service._write_local") as write_local,
        ):
            delete_tracker_item("item-1", "pushkar")

        write_local.assert_called_once_with([local_items[1]])

    def test_delete_reports_missing_item(self):
        collection = Mock()
        collection.delete_one.return_value = SimpleNamespace(deleted_count=0)

        with (
            patch("tracker_service.get_db", return_value={"tracker_items": collection}),
            patch("tracker_service._read_local", return_value=[]),
            self.assertRaisesRegex(ValueError, "Tracker item not found"),
        ):
            delete_tracker_item("missing", "pushkar")


if __name__ == "__main__":
    unittest.main()
