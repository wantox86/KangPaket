"""
KangPaket — Profile manager: CRUD profil ke disk, export/import JSON.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from app.config import PROFILES_DIR
from app.models.request_model import RequestProfile


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProfileManager:
    def __init__(self, profiles_dir: str = PROFILES_DIR) -> None:
        self._dir = profiles_dir
        os.makedirs(self._dir, exist_ok=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def load_all_profiles(self) -> list[RequestProfile]:
        """Load semua profil dari disk. File corrupt di-skip dengan warning."""
        profiles: list[RequestProfile] = []
        try:
            entries = os.listdir(self._dir)
        except OSError:
            return profiles

        for filename in sorted(entries):
            if not filename.endswith(".json") or filename.startswith("."):
                continue
            path = os.path.join(self._dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                profiles.append(RequestProfile.from_dict(data))
            except (json.JSONDecodeError, KeyError, TypeError, OSError) as e:
                print(f"[ProfileManager] Skip corrupt file {filename}: {e}")

        return profiles

    def save_profile(self, profile: RequestProfile) -> None:
        """Simpan satu profil ke disk (create atau update)."""
        profile.updated_at = _now_iso()
        path = os.path.join(self._dir, f"{profile.id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
        except OSError as e:
            raise RuntimeError(f"Gagal menyimpan profil '{profile.name}': {e}") from e

    def delete_profile(self, profile_id: str) -> None:
        """Hapus profil dari disk."""
        path = os.path.join(self._dir, f"{profile_id}.json")
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            raise RuntimeError(f"Failed to delete profile {profile_id}: {e}") from e

    def get_profile(self, profile_id: str) -> RequestProfile | None:
        """Load satu profil by ID."""
        path = os.path.join(self._dir, f"{profile_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return RequestProfile.from_dict(json.load(f))
        except (json.JSONDecodeError, OSError):
            return None

    def delete_collection(self, collection_name: str) -> list[str]:
        """Hapus semua profil dalam satu collection. Return list ID yang dihapus."""
        profiles = self.load_all_profiles()
        deleted_ids: list[str] = []
        for profile in profiles:
            if profile.collection == collection_name:
                try:
                    self.delete_profile(profile.id)
                    deleted_ids.append(profile.id)
                except RuntimeError as e:
                    print(f"[ProfileManager] Gagal hapus profil {profile.id}: {e}")
        return deleted_ids

    def duplicate_profile(self, profile: RequestProfile) -> RequestProfile:
        """Duplikat profil dengan UUID baru dan nama + ' (copy)'."""
        import copy
        new_profile           = copy.deepcopy(profile)
        new_profile.id        = str(uuid.uuid4())
        new_profile.name      = profile.name + " (copy)"
        new_profile.created_at = _now_iso()
        new_profile.updated_at = _now_iso()
        self.save_profile(new_profile)
        return new_profile

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export_profiles(self, profiles: list[RequestProfile], path: str) -> None:
        """Export daftar profil ke satu file JSON."""
        payload = {
            "version":     "1.0",
            "app":         "KangPaket",
            "exported_at": _now_iso(),
            "profiles":    [p.to_dict() for p in profiles],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except OSError as e:
            raise RuntimeError(f"Failed to export profiles: {e}") from e

    def import_profiles(self, path: str) -> list[RequestProfile]:
        """
        Import profil dari file JSON KangPaket.
        - ID konflik → generate UUID baru.
        - Nama konflik → tambahkan suffix ' (imported)'.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise RuntimeError(f"Failed to read import file: {e}") from e

        if not isinstance(data, dict) or "profiles" not in data:
            raise RuntimeError("Invalid file format — not a KangPaket export file.")

        existing      = self.load_all_profiles()
        existing_ids  = {p.id for p in existing}
        existing_names = {p.name for p in existing}

        imported: list[RequestProfile] = []
        for raw in data["profiles"]:
            try:
                profile = RequestProfile.from_dict(raw)
            except Exception:
                continue

            # Resolve ID conflict
            if profile.id in existing_ids:
                profile.id = str(uuid.uuid4())

            # Resolve name conflict
            if profile.name in existing_names:
                profile.name = profile.name + " (imported)"

            profile.updated_at = _now_iso()
            self.save_profile(profile)

            existing_ids.add(profile.id)
            existing_names.add(profile.name)
            imported.append(profile)

        return imported

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_collections(self) -> list[str]:
        """Return sorted unique collection names dari semua profil."""
        profiles = self.load_all_profiles()
        return sorted({p.collection for p in profiles})

    def get_profiles_by_collection(self) -> dict[str, list[RequestProfile]]:
        """Return profil dikelompokkan per collection, sorted by name."""
        profiles = self.load_all_profiles()
        grouped: dict[str, list[RequestProfile]] = {}
        for p in profiles:
            grouped.setdefault(p.collection, []).append(p)
        for col in grouped:
            grouped[col].sort(key=lambda p: p.name.lower())
        return dict(sorted(grouped.items()))
