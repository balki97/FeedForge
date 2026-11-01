# Guitar Pro export

FeedForge uses the unmodified PyGuitarPro 0.11 library, licensed under the GNU
Lesser General Public License, version 3 or later. Copyright its contributors.

Source: https://github.com/Perlence/PyGuitarPro/tree/v0.11
Package: https://pypi.org/project/PyGuitarPro/0.11/

The LGPL and GPL license texts are included in `licenses/`. The bundled
converter ships PyGuitarPro as editable Python source in `_internal/guitarpro/`
(inside the app's `resources/bin/psarc2feedpak/` directory). You can modify or
replace that library with a compatible version. FeedForge does not restrict
reverse engineering for debugging modifications to this LGPL library.

On macOS, changing bundled files invalidates the ad-hoc app signature; re-sign
your modified local application with `codesign --force --deep --sign - FeedForge.app`.
The rest of FeedForge remains under its existing MIT license.
