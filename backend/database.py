"""MongoDB database integration and user authentication for NutriTrust.

Stores users and personal health profiles (name, age, weight, gender, allergies, etc.).
Includes automatic persistent fallback to local storage if MongoDB Atlas is
unreachable (e.g. before IP whitelisting in MongoDB Atlas).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError

try:
    import certifi
    _CA_FILE = certifi.where()
except ImportError:
    _CA_FILE = None

from app_config import get_settings

logger = logging.getLogger(__name__)

_mongo_client: MongoClient | None = None
_LOCAL_DB_FILE = Path(__file__).resolve().parent / "data" / "users.json"


def _clean_doc_for_json(doc: dict[str, Any]) -> dict[str, Any]:
    copy_doc = dict(doc)
    if "_id" in copy_doc:
        copy_doc["_id"] = str(copy_doc["_id"])
    return copy_doc


def _read_local_users() -> list[dict[str, Any]]:
    """Read local users fallback file."""
    if not _LOCAL_DB_FILE.exists():
        return []
    try:
        with open(_LOCAL_DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("Could not read local users file: %s", exc)
        return []


def _write_local_users(users: list[dict[str, Any]]) -> None:
    """Save users to local fallback file safely."""
    try:
        _LOCAL_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        sanitized = [_clean_doc_for_json(u) for u in users]
        with open(_LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, indent=2)
    except Exception as exc:
        logger.error("Could not write local users file: %s", exc)


def get_client() -> MongoClient:
    """Return a cached MongoClient instance."""
    global _mongo_client
    if _mongo_client is None:
        settings = get_settings()
        uri = settings.mongodb_uri
        logger.info("Initializing MongoDB client (database=%s)", settings.mongodb_db_name)
        kwargs: dict[str, Any] = {
            "serverSelectionTimeoutMS": 4000,
            "connectTimeoutMS": 4000,
            "appname": "NutriTrust",
        }
        if _CA_FILE and ("+srv://" in uri or "ssl=true" in uri.lower() or "tls=true" in uri.lower()):
            kwargs["tlsCAFile"] = _CA_FILE

        _mongo_client = MongoClient(uri, **kwargs)
    return _mongo_client


def get_db() -> Database:
    """Return the NutriTrust database."""
    settings = get_settings()
    client = get_client()
    return client[settings.mongodb_db_name]


def get_users_collection() -> Collection:
    """Return the users collection with ensured unique index on username."""
    db = get_db()
    collection = db["users"]
    try:
        collection.create_index("username", unique=True)
    except Exception as exc:
        logger.warning("Could not ensure unique index on users: %s", exc)
    return collection


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random salt."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=100000,
    ).hex()
    return hashed, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Securely verify password against stored PBKDF2 hash and salt."""
    test_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(stored_hash, test_hash)


def clean_profile(raw_profile: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize user health profile fields."""
    if not raw_profile:
        return {
            "name": None,
            "age": None,
            "weight": None,
            "gender": None,
            "allergies": [],
            "allergy_other": None,
            "conditions": [],
            "condition_other": None,
            "preferences": [],
        }

    age = raw_profile.get("age")
    if age is not None and str(age).strip():
        try:
            age = int(age)
        except (ValueError, TypeError):
            age = None
    else:
        age = None

    weight = raw_profile.get("weight")
    if weight is not None and str(weight).strip():
        try:
            weight = float(weight)
        except (ValueError, TypeError):
            weight = None
    else:
        weight = None

    def _to_list(val: Any) -> list[str]:
        if isinstance(val, (list, set, tuple)):
            return [str(item).strip() for item in val if str(item).strip()]
        if isinstance(val, str) and val.strip():
            return [val.strip()]
        return []

    return {
        "name": str(raw_profile.get("name", "")).strip() or None,
        "age": age,
        "weight": weight,
        "gender": str(raw_profile.get("gender", "")).strip() or None,
        "allergies": _to_list(raw_profile.get("allergies")),
        "allergy_other": str(raw_profile.get("allergy_other", "")).strip() or None,
        "conditions": _to_list(raw_profile.get("conditions")),
        "condition_other": str(raw_profile.get("condition_other", "")).strip() or None,
        "preferences": _to_list(raw_profile.get("preferences")),
    }


def register_user(
    username: str,
    password: str,
    profile_data: Mapping[str, Any] | None = None,
    users_collection: Collection | None = None,
) -> dict[str, Any]:
    """Register a new user with hashed credentials and health profile."""
    cleaned_username = username.strip().lower()
    if not cleaned_username:
        raise ValueError("Username or email is required.")
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters long.")

    password_hash, salt = hash_password(password)
    profile = clean_profile(profile_data)
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "username": cleaned_username,
        "password_hash": password_hash,
        "salt": salt,
        "profile": profile,
        "created_at": now,
        "updated_at": now,
    }

    try:
        coll = users_collection if users_collection is not None else get_users_collection()
        coll.insert_one(dict(doc))
        logger.info("User registered in MongoDB: %s", cleaned_username)
    except DuplicateKeyError as exc:
        raise ValueError("A user with this username or email already exists.") from exc
    except Exception as exc:
        if users_collection is not None and not isinstance(exc, PyMongoError):
            raise
        logger.warning("MongoDB unavailable (%s), using local persistent storage for %s", exc, cleaned_username)
        local_users = _read_local_users()
        if any(u.get("username") == cleaned_username for u in local_users):
            raise ValueError("A user with this username or email already exists.")
        clean_doc = {
            "username": cleaned_username,
            "password_hash": password_hash,
            "salt": salt,
            "profile": profile,
            "created_at": now,
            "updated_at": now,
        }
        local_users.append(clean_doc)
        _write_local_users(local_users)

    return {
        "username": cleaned_username,
        "profile": profile,
        "created_at": now,
    }


def authenticate_user(
    username: str,
    password: str,
    users_collection: Collection | None = None,
) -> dict[str, Any]:
    """Verify credentials and return user profile information."""
    cleaned_username = username.strip().lower()
    if not cleaned_username or not password:
        raise ValueError("Username and password are required.")

    user: dict[str, Any] | None = None
    try:
        coll = users_collection if users_collection is not None else get_users_collection()
        user = coll.find_one({"username": cleaned_username})
    except Exception as exc:
        if users_collection is not None and not isinstance(exc, PyMongoError):
            raise
        logger.warning("MongoDB unavailable (%s), falling back to local storage for %s", exc, cleaned_username)

    if not user:
        local_users = _read_local_users()
        for u in local_users:
            if u.get("username") == cleaned_username:
                user = u
                break

    if not user:
        raise ValueError("Invalid username or password.")

    stored_hash = user.get("password_hash", "")
    salt = user.get("salt", "")

    if not verify_password(password, stored_hash, salt):
        raise ValueError("Invalid username or password.")

    return {
        "username": user["username"],
        "profile": clean_profile(user.get("profile")),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }


def get_profile(
    username: str,
    users_collection: Collection | None = None,
) -> dict[str, Any]:
    """Retrieve profile for a given username."""
    cleaned_username = username.strip().lower()
    if not cleaned_username:
        raise ValueError("Username is required.")

    user: dict[str, Any] | None = None
    try:
        coll = users_collection if users_collection is not None else get_users_collection()
        user = coll.find_one({"username": cleaned_username})
    except Exception as exc:
        if users_collection is not None and not isinstance(exc, PyMongoError):
            raise
        logger.warning("MongoDB unavailable (%s), checking local storage for %s", exc, cleaned_username)

    if not user:
        local_users = _read_local_users()
        for u in local_users:
            if u.get("username") == cleaned_username:
                user = u
                break

    if not user:
        raise ValueError("User not found.")

    return clean_profile(user.get("profile"))


def update_profile(
    username: str,
    profile_data: Mapping[str, Any],
    users_collection: Collection | None = None,
) -> dict[str, Any]:
    """Update personal health profile fields for a user."""
    cleaned_username = username.strip().lower()
    if not cleaned_username:
        raise ValueError("Username is required.")

    profile = clean_profile(profile_data)
    now = datetime.now(timezone.utc).isoformat()

    updated = False
    try:
        coll = users_collection if users_collection is not None else get_users_collection()
        result = coll.update_one(
            {"username": cleaned_username},
            {"$set": {"profile": profile, "updated_at": now}},
        )
        if result.matched_count > 0:
            updated = True
    except Exception as exc:
        if users_collection is not None and not isinstance(exc, PyMongoError):
            raise
        logger.warning("MongoDB unavailable (%s), updating local storage for %s", exc, cleaned_username)

    if not updated:
        local_users = _read_local_users()
        found = False
        for u in local_users:
            if u.get("username") == cleaned_username:
                u["profile"] = profile
                u["updated_at"] = now
                found = True
                break
        if found:
            _write_local_users(local_users)
            updated = True

    if not updated:
        raise ValueError("User not found.")

    return profile


_LOCAL_SCANS_FILE = Path(__file__).resolve().parent / "data" / "scans.json"
_LOCAL_PRODUCTS_FILE = Path(__file__).resolve().parent / "data" / "products.json"


def save_scan_and_product(
    scan_type: str,
    analysis_response: Mapping[str, Any],
    username: str | None = None,
    barcode: str | None = None,
) -> None:
    """Save scanned product and scan event to MongoDB 'products' and 'scans' collections."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        prod_analysis = analysis_response.get("product_analysis") or {}
        product_info = prod_analysis.get("product") or {}
        scoring = prod_analysis.get("scoring") or analysis_response.get("scoring") or {}

        product_name = product_info.get("name") or "Unknown Product"
        resolved_barcode = barcode or product_info.get("barcode") or analysis_response.get("barcode")
        cleaned_user = username.strip().lower() if username and username.strip() else "guest"

        scan_doc = {
            "username": cleaned_user,
            "scan_type": scan_type,
            "barcode": resolved_barcode,
            "product_name": product_name,
            "scoring": scoring,
            "product_analysis": prod_analysis,
            "created_at": now,
        }

        saved_to_mongo = False
        try:
            db = get_db()
            if resolved_barcode:
                db["products"].update_one(
                    {"barcode": str(resolved_barcode).strip()},
                    {
                        "$set": {
                            "barcode": str(resolved_barcode).strip(),
                            "name": product_name,
                            "brand": product_info.get("brands") or product_info.get("brand"),
                            "product_analysis": prod_analysis,
                            "scoring": scoring,
                            "updated_at": now,
                        },
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            db["scans"].insert_one(dict(scan_doc))
            saved_to_mongo = True
            logger.info("Saved product and scan to MongoDB for user=%s barcode=%s", cleaned_user, resolved_barcode)
        except Exception as exc:
            logger.warning("MongoDB unavailable for saving scan (%s), saving locally", exc)

        if not saved_to_mongo:
            try:
                _LOCAL_SCANS_FILE.parent.mkdir(parents=True, exist_ok=True)
                scans = []
                if _LOCAL_SCANS_FILE.exists():
                    with open(_LOCAL_SCANS_FILE, "r", encoding="utf-8") as f:
                        scans = json.load(f)
                scans.append(_clean_doc_for_json(scan_doc))
                with open(_LOCAL_SCANS_FILE, "w", encoding="utf-8") as f:
                    json.dump(scans[-200:], f, indent=2)
            except Exception as e:
                logger.warning("Could not save scan locally: %s", e)
    except Exception as exc:
        logger.warning("Error in save_scan_and_product: %s", exc)


def get_user_scans(username: str, limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve scan history for a user from MongoDB or local storage."""
    cleaned_username = username.strip().lower()
    try:
        db = get_db()
        cursor = db["scans"].find({"username": cleaned_username}).sort("created_at", -1).limit(limit)
        scans = []
        for doc in cursor:
            doc_copy = dict(doc)
            if "_id" in doc_copy:
                doc_copy["_id"] = str(doc_copy["_id"])
            scans.append(doc_copy)
        if scans:
            return scans
    except Exception as exc:
        logger.warning("Could not read scans from MongoDB: %s", exc)

    if _LOCAL_SCANS_FILE.exists():
        try:
            with open(_LOCAL_SCANS_FILE, "r", encoding="utf-8") as f:
                all_scans = json.load(f)
            matches = [s for s in all_scans if s.get("username") == cleaned_username]
            return list(reversed(matches[-limit:]))
        except Exception:
            return []
    return []
