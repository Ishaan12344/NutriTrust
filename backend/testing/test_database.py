"""Unit tests for MongoDB database integration, authentication, and health profiles."""

import unittest
from unittest.mock import MagicMock, patch

from database import (
    authenticate_user,
    clean_profile,
    get_profile,
    hash_password,
    register_user,
    update_profile,
    verify_password,
)


class FakeMongoCollection:
    """In-memory collection mock for MongoDB testing without live server."""

    def __init__(self):
        self.docs = []

    def create_index(self, key, unique=False):
        pass

    def insert_one(self, doc):
        from pymongo.errors import DuplicateKeyError

        if any(d.get("username") == doc.get("username") for d in self.docs):
            raise DuplicateKeyError("duplicate key")
        self.docs.append(dict(doc))
        return MagicMock(inserted_id="fake_id")

    def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    def update_one(self, query, update):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    doc.update(update["$set"])
                return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)


class DatabaseTests(unittest.TestCase):
    def test_clean_profile_defaults(self):
        profile = clean_profile(None)
        self.assertIsNone(profile["name"])
        self.assertIsNone(profile["age"])
        self.assertIsNone(profile["weight"])
        self.assertIsNone(profile["gender"])
        self.assertEqual(profile["allergies"], [])
        self.assertEqual(profile["conditions"], [])
        self.assertEqual(profile["preferences"], [])

    def test_clean_profile_parses_numeric_and_string_values(self):
        raw = {
            "name": " Alice ",
            "age": "28",
            "weight": "62.5",
            "gender": "Female",
            "allergies": ["Peanuts", "Soy"],
            "allergy_other": "Pollen",
            "conditions": ["Diabetes"],
            "preferences": ["Vegetarian"],
        }
        profile = clean_profile(raw)
        self.assertEqual(profile["name"], "Alice")
        self.assertEqual(profile["age"], 28)
        self.assertEqual(profile["weight"], 62.5)
        self.assertEqual(profile["gender"], "Female")
        self.assertEqual(profile["allergies"], ["Peanuts", "Soy"])
        self.assertEqual(profile["allergy_other"], "Pollen")
        self.assertEqual(profile["conditions"], ["Diabetes"])
        self.assertEqual(profile["preferences"], ["Vegetarian"])

    def test_password_hashing_and_verification(self):
        pw = "superSecret123"
        hashed, salt = hash_password(pw)
        self.assertTrue(verify_password(pw, hashed, salt))
        self.assertFalse(verify_password("wrongPassword", hashed, salt))

    def test_user_registration_and_authentication_flow(self):
        fake_coll = FakeMongoCollection()

        # Registration
        registered = register_user(
            username="testuser",
            password="securepassword",
            profile_data={"name": "Test User", "age": 30, "weight": 75.0, "allergies": ["Milk/dairy"]},
            users_collection=fake_coll,
        )
        self.assertEqual(registered["username"], "testuser")
        self.assertEqual(registered["profile"]["name"], "Test User")
        self.assertEqual(registered["profile"]["weight"], 75.0)

        # Duplicate registration fails
        with self.assertRaises(ValueError):
            register_user("testuser", "anotherpassword", users_collection=fake_coll)

        # Short password fails
        with self.assertRaises(ValueError):
            register_user("newuser", "123", users_collection=fake_coll)

        # Authentication success
        auth = authenticate_user("testuser", "securepassword", users_collection=fake_coll)
        self.assertEqual(auth["username"], "testuser")
        self.assertEqual(auth["profile"]["name"], "Test User")

        # Wrong password fails
        with self.assertRaises(ValueError):
            authenticate_user("testuser", "wrongpw", users_collection=fake_coll)

        # Unknown user fails
        with self.assertRaises(ValueError):
            authenticate_user("nonexistent", "password", users_collection=fake_coll)

    def test_profile_retrieval_and_update(self):
        fake_coll = FakeMongoCollection()
        register_user("bob", "password123", {"name": "Bob", "age": 40}, users_collection=fake_coll)

        # Fetch profile
        prof = get_profile("bob", users_collection=fake_coll)
        self.assertEqual(prof["name"], "Bob")
        self.assertEqual(prof["age"], 40)

        # Update profile (weight, allergies, conditions)
        updated = update_profile(
            "bob",
            {"name": "Bob Smith", "age": 41, "weight": 82.0, "allergies": ["Eggs"], "conditions": ["High blood pressure (hypertension)"]},
            users_collection=fake_coll,
        )
        self.assertEqual(updated["name"], "Bob Smith")
        self.assertEqual(updated["age"], 41)
        self.assertEqual(updated["weight"], 82.0)
        self.assertIn("Eggs", updated["allergies"])
        self.assertIn("High blood pressure (hypertension)", updated["conditions"])

        # Fetch updated profile
        prof2 = get_profile("bob", users_collection=fake_coll)
        self.assertEqual(prof2["weight"], 82.0)


if __name__ == "__main__":
    unittest.main()
