"""
Build script to create Transkeet.app bundle.

Usage:
    python setup.py

Creates dist/Transkeet.app with a proper CFBundleIdentifier so macOS can
grant Accessibility and Microphone permissions persistently.

The bundle uses a native Mach-O launcher that embeds the Python interpreter
via Py_Main. This means the actual running process IS the Transkeet binary
(not a separate Python process), so macOS TCC correctly attributes all
permissions — Accessibility, Input Monitoring, Microphone — to the app.
"""

import plistlib
import subprocess
import sysconfig
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP = DIST / "Transkeet.app"
CONTENTS = APP / "Contents"
MACOS = CONTENTS / "MacOS"
RESOURCES = CONTENTS / "Resources"

INFO_PLIST = {
    "CFBundleExecutable": "Transkeet",
    "CFBundleIdentifier": "com.arkham.transkeet",
    "CFBundleInfoDictionaryVersion": "6.0",
    "CFBundleName": "Transkeet",
    "CFBundlePackageType": "APPL",
    "CFBundleVersion": "0.1.0",
    "CFBundleShortVersionString": "0.1.0",
    "LSUIElement": True,
    "NSMicrophoneUsageDescription": (
        "Transkeet needs microphone access to record and transcribe speech."
    ),
    "NSAccessibilityUsageDescription": (
        "Transkeet needs Accessibility access to listen for hotkeys and paste transcribed text."
    ),
}

# Resolve paths for the C launcher
_venv = ROOT / ".venv"
_py_prefix = Path(sysconfig.get_config_var("prefix"))
_py_include = sysconfig.get_config_var("INCLUDEPY")
_py_libdir = sysconfig.get_config_var("LIBDIR")
_py_ldlib = sysconfig.get_config_var("LDLIBRARY")  # e.g. libpython3.12.dylib
# Extract the -l flag name: libpython3.12.dylib → python3.12
_py_link = _py_ldlib.removeprefix("lib").removesuffix(".dylib")

LAUNCHER_C = f"""\
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <ApplicationServices/ApplicationServices.h>
#include <CoreFoundation/CoreFoundation.h>

static CGEventRef _noop_tap(CGEventTapProxy proxy, CGEventType type,
                            CGEventRef event, void *info) {{
    return event;
}}

int main(int argc, char *argv[]) {{
    /* ── TCC: Request Accessibility ─────────────────────────────────── */
    CFMutableDictionaryRef opts = CFDictionaryCreateMutable(
        NULL, 1,
        &kCFTypeDictionaryKeyCallBacks,
        &kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(opts, kAXTrustedCheckOptionPrompt, kCFBooleanTrue);
    Boolean trusted = AXIsProcessTrustedWithOptions(opts);
    CFRelease(opts);

    if (!trusted) {{
        fprintf(stderr,
            "Transkeet: Accessibility not yet granted.\\n"
            "  System Settings > Privacy & Security > Accessibility\\n");
    }}

    /* ── TCC: Trigger Input Monitoring prompt ───────────────────────── */
    CGEventMask mask = CGEventMaskBit(kCGEventFlagsChanged);
    CFMachPortRef tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionListenOnly,
        mask, _noop_tap, NULL);
    if (tap) {{
        CFRelease(tap);
    }} else {{
        fprintf(stderr,
            "Transkeet: Input Monitoring not yet granted.\\n"
            "  System Settings > Privacy & Security > Input Monitoring\\n");
    }}

    /* ── Environment ────────────────────────────────────────────────── */
    setenv("PYTHONUNBUFFERED", "1", 1);

    /* Add Homebrew to PATH (launchd uses a minimal PATH) */
    const char *path = getenv("PATH");
    if (path) {{
        char new_path[4096];
        snprintf(new_path, sizeof(new_path),
            "/opt/homebrew/bin:/usr/local/bin:%s", path);
        setenv("PATH", new_path, 1);
    }} else {{
        setenv("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin", 1);
    }}

    /* Point Python at the base install for stdlib, venv for packages */
    setenv("PYTHONHOME", "{_py_prefix}", 1);
    setenv("PYTHONPATH", "{ROOT / 'src'}:{_venv / 'lib' / f'python{sysconfig.get_python_version()}' / 'site-packages'}", 1);
    setenv("VIRTUAL_ENV", "{_venv}", 1);

    /* ── Run Python inline (single process, no fork/exec) ──────────── */
    wchar_t *py_argv[] = {{
        L"transkeet",
        L"-c",
        L"from transkeet.app import main; main()",
        NULL
    }};
    return Py_Main(3, py_argv);
}}
"""


def build():
    # Clean previous build
    if APP.exists():
        import shutil
        shutil.rmtree(APP)

    # Create directory structure
    for d in (MACOS, RESOURCES):
        d.mkdir(parents=True)

    # Write Info.plist
    with open(CONTENTS / "Info.plist", "wb") as f:
        plistlib.dump(INFO_PLIST, f)

    # Compile native launcher with embedded Python
    launcher_path = MACOS / "Transkeet"
    with tempfile.NamedTemporaryFile(suffix=".c", mode="w", delete=False) as f:
        f.write(LAUNCHER_C)
        c_path = f.name

    subprocess.run(
        [
            "clang", "-Wall", "-O2",
            f"-I{_py_include}",
            f"-L{_py_libdir}",
            f"-l{_py_link}",
            f"-Wl,-rpath,{_py_libdir}",
            "-framework", "ApplicationServices",
            "-framework", "CoreFoundation",
            "-o", str(launcher_path),
            c_path,
        ],
        check=True,
    )
    Path(c_path).unlink()

    # Ad-hoc codesign so TCC has a stable identity
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(APP)],
        check=True,
    )

    print(f"Built {APP}")
    print(f"  Bundle ID: {INFO_PLIST['CFBundleIdentifier']}")
    print(f"  Launcher:  {launcher_path} (compiled Mach-O, embeds Python)")
    print(f"  Info.plist: {CONTENTS / 'Info.plist'}")


if __name__ == "__main__":
    build()
