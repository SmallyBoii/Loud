# Third-party notices

Loud itself is released under the [MIT license](LICENSE). `Loud.exe` is built with PyInstaller and contains the programs and libraries below, unmodified. Each keeps its own license.

| Component | Version | License | Source |
|---|---|---|---|
| CPython (the Python runtime and standard library, including `tkinter`) | 3.12 in the release build | PSF-2.0 | https://www.python.org |
| Tcl/Tk (the toolkit behind `tkinter`) | 8.6, as shipped with that Python | Tcl/Tk license (BSD-style) | https://www.tcl-lang.org |
| NumPy | 2.x | BSD-3-Clause | https://github.com/numpy/numpy |
| OpenBLAS and the other libraries NumPy ships | as bundled in the NumPy wheel | BSD-3-Clause and others, listed in the NumPy license file | https://github.com/OpenMathLib/OpenBLAS |
| Microsoft Visual C++ runtime (`vcruntime140`, `msvcp140`) | as shipped with Python and NumPy | Microsoft redistributable terms | https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files |
| PyInstaller bootloader | 6.x | GPL-2.0 with the PyInstaller bootloader exception (programs built with it may use any license) | https://github.com/pyinstaller/pyinstaller |

Copies of the license texts are in the [`licenses`](licenses) folder (and in the release zip). The NumPy file also contains the licenses of the libraries bundled in the NumPy wheel.

## Not bundled

- **VB-Cable** (https://vb-audio.com/Cable/, by VB-Audio): a virtual audio device a PC with only one sound output can use as Loud's silent input. It is a separate download from its publisher, under its own terms. Loud does not include it, install it, or talk to its installer; it only offers a link to the publisher's page.
- **Spotify** is a trademark of its owner. Loud is an independent project, not affiliated with or endorsed by Spotify or VB-Audio.
