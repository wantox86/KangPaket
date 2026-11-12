# Releasing KangPaket

KangPaket is a desktop app packaged with **PyInstaller** (`--onefile`). It is not a Docker service and not an APK, so
"deploy" means: build the three binaries, verify them, upload them, and let the maintainer publish a GitHub Release.
All three platforms can be built from a single Apple Silicon Mac (macOS native, Linux and Windows via Docker emulation).
Total time is roughly 5-7 minutes once the Docker images are cached.

## 1. Versioning

- Semantic versioning, tags look like `vX.Y.Z`, release branches look like `release/vX.Y.Z`.
- The version lives in **`app/version.py`** (`__version__`) and must be identical in **`pyproject.toml`** (`version = "..."`).
  `tests/test_version.py` enforces that they agree.
- `app/config.py` does **not** hold a version of its own: it re-exports `__version__` from `app/version.py` as `APP_VERSION`.
  Never edit a version there.
- Branch flow: feature branches are squash-merged into `release/vX.Y.Z`; the maintainer merges `release/vX.Y.Z` into `main`;
  the release manager then tags the merge commit on `main` as `vX.Y.Z`. Agents never merge to `main`.

## 2. Pre-flight

1. Work from a **fresh clone** in a temporary directory, check out the target tag/branch/SHA and record the SHA.
2. Confirm the version number in `app/version.py` and `pyproject.toml` is the intended one.
3. Build exactly what is checked in: do not change code or version during a release build, and do not push.
4. Run the test suite inside a venv with `requirements.txt` installed. `requirements.txt` does **not** include pytest, so install it first:
   `pip install pytest && python -m pytest -q`.

## 3. Build

### macOS arm64 (native)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pyinstaller
./build.sh macos
```

`build.sh macos` also stamps `CFBundleShortVersionString` / `CFBundleVersion` from `app/version.py` and re-signs ad-hoc.
Package with `ditto` (plain `zip` breaks the code signature):

```bash
ditto -c -k --keepParent dist/KangPaket.app KangPaket-macos-arm64.app.zip
```

### Linux x86-64 (Docker, amd64 emulation)

Export the sources with `git archive HEAD | tar -x -C <src>`, then:

```bash
docker run --rm --platform linux/amd64 -v SRC:/src -v OUT:/out -v SCRIPTS:/s:ro ubuntu:22.04 bash /s/linux.sh
```

`linux.sh` installs `python3 python3-venv python3-pip python3-tk binutils`, creates a venv, runs
`pip install -r requirements.txt pyinstaller`, then:

```bash
python -m PyInstaller --noconfirm --clean --onefile --name KangPaket \
  --add-data "data:data" --add-data "assets:assets" \
  --collect-all customtkinter --collect-all darkdetect \
  --hidden-import customtkinter --hidden-import darkdetect --hidden-import tkinter --hidden-import _tkinter \
  --hidden-import PIL --hidden-import PIL.Image --hidden-import httpx --hidden-import jsonpath_ng \
  --windowed --icon assets/KangPaket-ico.png main.py
cp dist/KangPaket /out/KangPaket-linux-x86_64
```

### Windows x86-64 (Docker + Wine)

Image `tobix/pywine:3.12`, run in parallel with the Linux build if you like:

1. `wine python -m pip install -r requirements.txt pyinstaller`
2. Create `assets/KangPaket-ico.ico` from the PNG with Pillow (same call as `build.bat`).
3. `wine python -m PyInstaller` with the **same flags as Linux**, except the data separator is `;`
   (`--add-data "data;data" --add-data "assets;assets"`) and `--icon assets/KangPaket-ico.ico`.
4. `cp dist/KangPaket.exe /out/KangPaket-windows-x86_64.exe`

Keep the flag list identical to `build.bat` / `build.sh`; if either script changes, update the commands above.

### Docker credential helper hang

On the build Mac, `docker` may hang on `docker-credential-desktop` (keychain prompt that cannot be answered non-interactively).
Workaround: `export DOCKER_CONFIG=/tmp/<dir>` containing `config.json` with `{}` **plus** a symlink `cli-plugins` pointing to
`~/.docker/cli-plugins` (without the symlink `docker compose` disappears).

## 4. Verify

- `file` on each artifact: ELF 64-bit x86-64 (Linux), PE32+ GUI x86-64 (Windows), Zip (macOS).
- macOS: extract the zip and check the extracted app (not the original): `plutil -p KangPaket.app/Contents/Info.plist`
  shows the right version, and `codesign --verify --deep --strict KangPaket.app` passes.
- Confirm app modules (e.g. `app.core.sync_*`, `app.version`) are present in the bundles.
- macOS smoke test: launch with an isolated `HOME` for at least 15 seconds (data dir is `$HOME/Library/Application Support/KangPaket`).
  Do not use AppleScript / System Events / screencapture on the build machine; they hang or are blocked.
- Be honest in the release report: the Linux binary and the Windows `.exe` have **not been executed**, and the `.exe` is built
  under Wine and has not been tested on real Windows.

## 5. Upload and publish

1. Upload to the shared build drop (temp area of the file server): `temp/KangPaket-v<ver>-<sha7>/` with directory mode 750 and
   file mode 640, plus a `BUILD-INFO.txt` (version, full SHA, build date, sha256 of each file, what was and was not verified).
   Compare the sha256 computed locally with the one on the server. The `temp` area is cleaned automatically
   (files older than 3 days), so remind the maintainer.
2. The maintainer publishes the GitHub Release: tag `v<ver>` targeting `main`, assets named
   `KangPaket-windows-x86_64.exe`, `KangPaket-linux-x86_64`, `KangPaket.app.zip` (the macOS zip, renamed). Release notes in English.
3. After publishing, update the website repo (`KangPaket-web`) through a PR to `main`: download version/date and the three links,
   the hero badge, and the changelog; check that the download URLs return 200. Merging deploys GitHub Pages.

### macOS Gatekeeper note (unsigned / ad-hoc)

The app is not notarized, so Gatekeeper refuses it at first launch. Either allow it in System Settings > Privacy & Security >
Open Anyway, or run `xattr -dr com.apple.quarantine KangPaket.app`. Right-click > Open is not enough on macOS Sequoia and later.
An approval granted on one Mac does not carry over to other users' Macs.

## 6. Rollback

Release artifacts are immutable files, so rollback is a republish of the previous version:

1. In GitHub Releases, mark the bad release as pre-release or delete it (maintainer only), and re-publish the previous
   release's assets as "latest" if needed.
2. Revert the website PR (download version, links, badge) so the site points at the previous version.
3. Keep the previous version's build folder / assets until the new release is confirmed good.
4. If the tag itself is wrong, do not move it silently: cut a new patch version (`vX.Y.Z+1`) with the fix.

## 7. Release report checklist

Report to the maintainer: version, tag, commit SHA, test result, per-platform artifact name + sha256, what was verified,
what was not (see section 4), and where the files were uploaded.
