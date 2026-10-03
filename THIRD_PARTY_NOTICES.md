# Third-party notices

Orbit is made by Josef Kotran. The installer ships the components below with Orbit, and Orbit downloads a few more
on first use. Each component keeps its own licence. In an installed Orbit
(`%LOCALAPPDATA%\Programs\Orbit`) you'll find the licence texts here:

- `licenses\` has the GNU GPL 3.0 and LGPL 3.0 texts and `python-packages.txt`, which lists every bundled Python
  package with its version and licence. The build script writes that list.
- `runtime\LICENSE.txt` is Python's licence, including the components Python bundles.
- `runtime\Lib\site-packages\<package>-<version>.dist-info\` has each Python package's own licence files.
- `whisper\LICENSE` (whisper.cpp/ggml) and `whisper\LICENSE-winpthreads`.

## Bundled in the installer

| Component | Licence | Where | Source |
|---|---|---|---|
| Python 3.13.7 (Windows embeddable package) | PSF-2.0. It bundles OpenSSL (Apache-2.0), SQLite (public domain), libffi (MIT), expat (MIT), bzip2, xz, zlib and mpdecimal (permissive). | `runtime\` | python.org |
| PySide6, Shiboken6 6.11.2 (Qt for Python) | LGPL-3.0-only (or GPL-2.0/3.0, or a commercial licence) | `runtime\Lib\site-packages\PySide6`, `shiboken6` | download.qt.io/official_releases/QtForPython |
| Qt 6.11.2: QtCore, QtGui, QtWidgets, QtTextToSpeech, QtSvg and their plugins | LGPL-3.0-only. Qt's own third-party parts are listed at doc.qt.io/qt-6/licenses-used-in-qt.html. | `…\PySide6\Qt6*.dll`, `…\PySide6\plugins` | download.qt.io/official_releases/qt/6.11/6.11.2 |
| Microsoft Visual C++ runtime (msvcp140*.dll, vcruntime140*.dll, concrt140.dll, vcomp140.dll, vccorlib140.dll) | Microsoft Visual Studio "Distributable Code" terms. The PySide6 wheels ship these files; the build copies them next to python.exe. | `runtime\` | Microsoft |
| numpy 2.5.3 | BSD-3-Clause. It bundles OpenBLAS and LAPACK (BSD-3-Clause), plus parts under 0BSD, MIT, Zlib and CC0-1.0 (see its dist-info). | site-packages | numpy.org |
| sounddevice 0.5.6 | MIT | site-packages | github.com/spatialaudio/python-sounddevice |
| PortAudio (`libportaudio64bit.dll`, the build without ASIO) | MIT-style (PortAudio licence) | `…\_sounddevice_data` | portaudio.com |
| cffi, pycparser | MIT-0, BSD-3-Clause | site-packages | PyPI |
| pynput 1.8.2 | LGPL-3.0 | site-packages | github.com/moses-palmer/pynput |
| six | MIT | site-packages | PyPI |
| requests 2.34.2, urllib3, idna, charset-normalizer, certifi | Apache-2.0, MIT, BSD-3-Clause, MIT, MPL-2.0 | site-packages | PyPI |
| piper-tts 1.8.0 (left out of a `--without-piper` build) | **GPL-3.0-or-later** | `…\site-packages\piper` | github.com/OHF-Voice/piper1-gpl |
| espeak-ng, compiled into `piper\espeakbridge.pyd`, plus `piper\espeak-ng-data` | **GPL-3.0-or-later** | `…\site-packages\piper` | github.com/espeak-ng/espeak-ng |
| Piper's helper models: g2pW (Apache-2.0), Hebrew nakdimon (see `piper\hebrew\LICENSE`) | as stated | `…\site-packages\piper` | PyPI piper-tts |
| onnxruntime 1.30.0 (left out without Piper) | MIT. Its own third-party notices are in `onnxruntime\ThirdPartyNotices.txt`. | site-packages | github.com/microsoft/onnxruntime |
| flatbuffers, protobuf, packaging, pathvalidate (Piper/onnxruntime dependencies) | Apache-2.0, BSD-3-Clause, Apache-2.0 OR BSD-2-Clause, MIT | site-packages | PyPI |
| whisper.cpp 1.9.4 and ggml (`whisper-server.exe`, `libwhisper.dll`, `ggml*.dll`) | MIT, Copyright (c) 2023-2026 The ggml authors | `whisper\` | github.com/ggml-org/whisper.cpp |
| Compiled into whisper-server: cpp-httplib (MIT, (c) Yuji Hirose), nlohmann/json 3.11.2 (MIT, (c) 2013-2022 Niels Lohmann), miniaudio/dr_wav (public domain or MIT-0, David Reid), Vulkan-Headers (Apache-2.0 / MIT) | as stated | `whisper\` | whisper.cpp source tree |
| MinGW-w64 winpthreads (`libwinpthread-1.dll`) | MIT, plus BSD-style for the parts derived from Lockless Inc. (full text in `whisper\LICENSE-winpthreads`) | `whisper\` | mingw-w64.org |
| GCC runtime (libgcc, libstdc++), linked statically into the whisper DLLs | GPL-3.0 with the GCC Runtime Library Exception. No obligations for the compiled program. | `whisper\` | gcc.gnu.org |
| Inno Setup 6.7.3 (the installer and uninstaller program) | Inno Setup licence (permissive; commercial users are asked to buy a commercial licence) | `Orbit-Setup-*.exe`, `unins000.exe` | jrsoftware.org |

### What the LGPL asks of us (Qt, PySide6, pynput)

- Qt and PySide6 are unmodified, dynamically linked DLLs and Python modules. You may replace them with your own
  compatible build. Swap the files in `runtime\Lib\site-packages\PySide6` and `shiboken6`. pynput is plain Python
  source in `runtime\Lib\site-packages\pynput`, and you can edit or replace it.
- Source code: Qt 6.11.2 and PySide6 6.11.2 are at download.qt.io (links above). pynput 1.8.2 is on PyPI and GitHub.
  On request, Josef Kotran will send the exact source of every LGPL/GPL component in this installer for 3 years
  after the release.

### Piper and espeak-ng (GPL-3.0-or-later)

Orbit loads Piper into its own process. The GPL therefore covers Orbit as distributed together with Piper. A build
that includes Piper may only be distributed under GPL-3.0-compatible terms, with Orbit's source available.
`build_installer.py --without-piper` makes a build without Piper and onnxruntime. In that build, Orbit reads aloud
with the Windows voice only.

## Downloaded by Orbit on first use (not in the installer)

| Component | Licence | From |
|---|---|---|
| Whisper models large-v3 and large-v3-turbo (OpenAI), converted to ggml | MIT | huggingface.co/ggerganov/whisper.cpp |
| Piper voice cs_CZ-jirka-medium | Dataset CC0 (OHF-Voice/voice-datasets). **However,** the voice is fine-tuned from the en_US "lessac" voice. lessac was trained on the Blizzard Challenge 2013 Lessac data, whose licence allows research use only and excludes any commercial use, including voice synthesis products. | huggingface.co/rhasspy/piper-voices |
| Piper voice cs_CZ-kasandra-medium | Dataset CC BY 4.0, author Ondřej Šimek. **Attribution required.** | huggingface.co/rhasspy/piper-voices |

## Used but not shipped

- **Claude Code** (Anthropic): each user installs it with Anthropic's official installer and signs in with their own
  account in Claude Code itself. Anthropic's terms apply. Orbit never handles Claude passwords or tokens.
- **Windows voices** (Microsoft Jakub and others) and the **Vulkan driver** (`vulkan-1.dll`) are parts of Windows or
  the graphics driver.
