"""
Postman import keeps folder structure (root = chosen/typed name, sub-path kept).

Run: PYTHONPATH=. python -m unittest tests.test_import_structure -v
Needs a display (real Tk). Skipped automatically if Tk cannot start.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest

from app.core.postman_importer import PostmanImportResult
from app.core.profile_manager import ProfileManager
from app.models.request_model import RequestProfile
from app.ui.postman_import_dialog import rebase_collection


def _result(n_root: int, n_sub: int, root: str = "btpns") -> PostmanImportResult:
    profiles = [RequestProfile(name=f"root req {i}", url="http://x/", collection=root) for i in range(n_root)]
    for i in range(n_sub):
        sub = f"{root} / KOMODO / svc{i % 3} / BETA" if i % 2 else f"{root} / KOMODO"
        profiles.append(RequestProfile(name=f"sub req {i}", url="http://x/", collection=sub))
    return PostmanImportResult(
        collection_name=root, total_items=len(profiles), profiles=profiles, warnings=[], skipped=[],
    )


class RebaseTests(unittest.TestCase):
    def test_default_root_unchanged(self):
        self.assertEqual(rebase_collection("btpns / KOMODO / prs-service / BETA", "btpns", "btpns"),
                         "btpns / KOMODO / prs-service / BETA")

    def test_renamed_root_replaces_only_first_segment(self):
        self.assertEqual(rebase_collection("btpns / KOMODO / prs-service / BETA", "btpns", "My Root"),
                         "My Root / KOMODO / prs-service / BETA")

    def test_no_subfolder_goes_directly_under_root(self):
        self.assertEqual(rebase_collection("btpns", "btpns", "My Root"), "My Root")

    def test_root_name_that_is_prefix_of_other_name(self):
        # 'btpns2 / X' must not be treated as sub-path of 'btpns'
        self.assertEqual(rebase_collection("btpns2 / X", "btpns", "R"), "btpns2 / X")


class DialogImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import customtkinter as ctk
        try:
            cls.root = ctk.CTk()
        except Exception as e:  # no display
            raise unittest.SkipTest(f"Tk unavailable: {e}")
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kp_test_")
        self.pm = ProfileManager(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _run(self, result, new_root: str | None = None) -> set[str]:
        from app.ui.postman_import_dialog import PostmanImportDialog
        dlg = PostmanImportDialog(self.root, "x.json", result, self.pm)
        self.root.update()
        if new_root is not None:
            dlg._new_col_var.set(new_root)
        dlg._select_all(True)
        dlg._do_import()
        self.root.update()
        return {p.collection for p in self.pm.load_all_profiles()}

    def _check(self, n_root, n_sub, new_root, large):
        result = _result(n_root, n_sub)
        from app.ui.postman_import_dialog import LARGE_IMPORT_THRESHOLD
        self.assertEqual(len(result.profiles) > LARGE_IMPORT_THRESHOLD, large)
        root = new_root or "btpns"
        got = self._run(result, new_root)
        expected = {f"{root}"} | {f"{root} / KOMODO"} | {f"{root} / KOMODO / svc{i} / BETA" for i in range(3)}
        if n_root == 0:
            expected.discard(root)
        self.assertEqual(len(self.pm.load_all_profiles()), n_root + n_sub)
        self.assertEqual(got, expected)

    def test_small_default_root(self):
        self._check(2, 8, None, large=False)

    def test_small_renamed_root(self):
        self._check(2, 8, "Renamed", large=False)

    def test_small_no_root_level_requests(self):
        self._check(0, 8, None, large=False)

    def test_large_default_root(self):
        self._check(5, 40, None, large=True)

    def test_large_renamed_root(self):
        self._check(5, 40, "Renamed", large=True)


if __name__ == "__main__":
    unittest.main()
