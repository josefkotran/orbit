"""Favourite folders (app/favorites.py, the + above the panel): the list keeps each folder once, names that clash show
the folder above, a new repo goes where most of them are, its name must be one Windows takes, and it's made with git
init (when git is here) or not at all; config.json keeps the list clean. Folders are made in a temporary one.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import json
import logging
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output

from app import config, favorites  # noqa: E402


class Folders(unittest.TestCase):
    def test_each_folder_once_full_paths_only(self):
        self.assertEqual(favorites.clean([r"C:\Users\josef\ondra", "C:/Users/josef/Ondra/", r"C:\Users\josef\orbit",
                                          "ondra", "", None, 5, r"  C:\Users\josef\m-tex  "]),
                         [r"C:\Users\josef\ondra", r"C:\Users\josef\orbit", r"C:\Users\josef\m-tex"])
        self.assertEqual(favorites.clean("C:\\x"), [])
        self.assertEqual(favorites.add([r"C:\a"], "c:/A"), [r"C:\a"])
        self.assertTrue(favorites.contains([r"C:\Users\josef\ondra"], "c:/users/josef/ONDRA"))

    def test_names_and_order(self):
        folders = [r"C:\Users\josef\orbit", r"C:\Users\josef\ondra\web", r"C:\Users\josef\hommel-portal",
                   r"D:\weby\web"]
        self.assertEqual(favorites.ordered(folders)[0], r"C:\Users\josef\hommel-portal")
        names = favorites.labels(folders)
        self.assertEqual(names[r"C:\Users\josef\orbit"], "orbit")
        self.assertEqual(names[r"C:\Users\josef\ondra\web"], "web (ondra)")  # two "web": the folder above too
        self.assertEqual(names[r"D:\weby\web"], "web (weby)")

    def test_new_repo_goes_where_most_of_them_are(self):
        home = tempfile.mkdtemp(prefix="orbit-test-home-")
        self.addCleanup(shutil.rmtree, home, True)
        other = os.path.join(home, "jinde")
        os.mkdir(other)
        folders = [os.path.join(home, "a"), os.path.join(home, "b"), os.path.join(other, "c")]
        self.assertEqual(os.path.normcase(favorites.default_parent(folders)), os.path.normcase(home))
        gone = [r"Q:\nikde\a", r"Q:\nikde\b"]
        self.assertEqual(favorites.default_parent(gone), str(Path.home()))
        self.assertEqual(favorites.default_parent([]), str(Path.home()))

    def test_names_windows_takes(self):
        for good in ("ondra", "hommel-portal", "můj projekt", "web.cz", "a" * 100):
            self.assertEqual(favorites.name_problem(good), "", good)
        for bad in ("", "  ", "a/b", "a\\b", "a:b", 'a"b', "a?", "a*", "a<b>", "tečka.", "con", "CON", "nul.txt",
                    "lpt1", "com9", "a" * 101, "x\ty"):
            self.assertTrue(favorites.name_problem(bad), bad)


class Create(unittest.TestCase):
    def setUp(self):
        self.parent = tempfile.mkdtemp(prefix="orbit-test-repo-")
        self.addCleanup(shutil.rmtree, self.parent, True)

    def test_a_folder_without_git(self):
        path, problem = favorites.create(self.parent, " ondra ", git=False)
        self.assertEqual(path, os.path.join(self.parent, "ondra"))
        self.assertTrue(os.path.isdir(path))
        self.assertFalse(os.path.exists(os.path.join(path, ".git")))
        self.assertEqual(problem, "")

    @unittest.skipUnless(favorites.git_exe(), "git tu není")
    def test_with_git_init(self):
        path, problem = favorites.create(self.parent, "s gitem", git=True)
        self.assertEqual(problem, "")
        self.assertTrue(os.path.isdir(os.path.join(path, ".git")))

    def test_without_git_installed_the_folder_still_comes(self):
        with mock.patch.object(favorites, "git_exe", return_value=None):
            path, problem = favorites.create(self.parent, "bez gitu", git=True)
        self.assertTrue(os.path.isdir(path))
        self.assertIn("git", problem)

    def test_refused(self):
        os.mkdir(os.path.join(self.parent, "je"))
        for parent, name in ((self.parent, "je"), (self.parent, "con"), (self.parent, "a/b"),
                             (os.path.join(self.parent, "neni"), "x"), (r"\\server\sdileni", "x"), ("relativni", "x"),
                             ("", "x")):
            with self.assertRaises(ValueError, msg=(parent, name)):
                favorites.create(parent, name, git=False)
        self.assertEqual(os.listdir(self.parent), ["je"])


class Config(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: config.CONFIG_PATH.unlink(missing_ok=True))
        config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    def load(self, value):
        config.CONFIG_PATH.write_text(json.dumps({"favorite_folders": value}), encoding="utf-8")
        return config.load()["favorite_folders"]

    def test_kept_clean(self):
        self.assertEqual(config.DEFAULTS["favorite_folders"], [])
        self.assertEqual(self.load([r"C:\a", "c:/A", "relativni"]), [r"C:\a"])
        self.assertEqual(self.load("C:\\a"), [])  # a wrong type: the default
        self.assertEqual(self.load([r"C:\a", 5]), [])


if __name__ == "__main__":
    unittest.main()
