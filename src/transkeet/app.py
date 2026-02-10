import threading
import time

import numpy as np
import rumps
import sounddevice as sd

from transkeet.config import build_vocabulary_replacements, ensure_config
from transkeet.transcriber import Transcriber

# ── Hotkey helpers ──────────────────────────────────────────────────────────

# Map config names → pynput key objects
_MODIFIER_MAP = {
    "cmd": "Key.cmd",
    "command": "Key.cmd",
    "cmd_r": "Key.cmd_r",
    "cmd_l": "Key.cmd_l",
    "shift": "Key.shift",
    "shift_r": "Key.shift_r",
    "shift_l": "Key.shift_l",
    "ctrl": "Key.ctrl",
    "control": "Key.ctrl",
    "ctrl_r": "Key.ctrl_r",
    "ctrl_l": "Key.ctrl_l",
    "alt": "Key.alt",
    "option": "Key.alt",
    "alt_r": "Key.alt_r",
    "alt_l": "Key.alt_l",
}


def _parse_hotkey(spec: str):
    """Parse a hotkey string like 'cmd+shift+space' into a pynput-compatible set."""
    from pynput.keyboard import Key, KeyCode

    parts = [p.strip().lower() for p in spec.split("+")]
    keys = set()
    for part in parts:
        if part in _MODIFIER_MAP:
            keys.add(getattr(Key, _MODIFIER_MAP[part].split(".")[1]))
        elif len(part) == 1:
            keys.add(KeyCode.from_char(part))
        else:
            # Try as a Key attribute (e.g. 'space', 'f1', 'esc')
            try:
                keys.add(getattr(Key, part))
            except AttributeError:
                raise ValueError(
                    f"Unknown key '{part}' in hotkey '{spec}'. "
                    f"Use modifier names (cmd/shift/ctrl/alt) or key names (space/a/f1/...)."
                )
    return keys


# ── Clipboard + paste via PyObjC ────────────────────────────────────────────


def _get_clipboard() -> str | None:
    """Read the current clipboard string (or None)."""
    from AppKit import NSPasteboard, NSStringPboardType

    pb = NSPasteboard.generalPasteboard()
    return pb.stringForType_(NSStringPboardType)


def _set_clipboard(text: str):
    """Write a string to the clipboard."""
    from AppKit import NSPasteboard, NSStringPboardType

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSStringPboardType)


def _simulate_paste():
    """Simulate Cmd+V using Quartz CoreGraphics events."""
    import Quartz

    # Key code 9 = 'v' on macOS
    V_KEYCODE = 9

    source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateCombinedSessionState)

    # Cmd down + V down
    event_down = Quartz.CGEventCreateKeyboardEvent(source, V_KEYCODE, True)
    Quartz.CGEventSetFlags(event_down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, event_down)

    # Cmd down + V up
    event_up = Quartz.CGEventCreateKeyboardEvent(source, V_KEYCODE, False)
    Quartz.CGEventSetFlags(event_up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGAnnotatedSessionEventTap, event_up)


def _paste_and_restore(text: str):
    """Copy text to clipboard, paste it, then restore previous clipboard."""
    saved = _get_clipboard()
    _set_clipboard(text)
    time.sleep(0.05)
    _simulate_paste()
    time.sleep(0.15)
    # Restore
    if saved is not None:
        _set_clipboard(saved)
    else:
        from AppKit import NSPasteboard

        NSPasteboard.generalPasteboard().clearContents()


# ── Menu bar app ────────────────────────────────────────────────────────────

ICON_IDLE = "\U0001F99C"  # 🦜
ICON_RECORDING = "\U0001F534"  # 🔴
ICON_TRANSCRIBING = "\U0001F504"  # 🔄


def _get_input_device_name() -> str:
    """Return the name of the default input audio device."""
    try:
        info = sd.query_devices(kind="input")
        return info["name"]
    except Exception:
        return "Unknown"


class TranskeetApp(rumps.App):
    def __init__(self, config: dict):
        super().__init__(ICON_IDLE, quit_button="Quit")

        self._config = config
        self._transcriber = Transcriber(config["model"])
        self._recording = False
        self._audio_frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._hotkey_keys = _parse_hotkey(config["hotkey"])
        self._pressed_keys: set = set()
        self._listener = None
        self._lock = threading.Lock()
        self._hotkey_recording = False  # True when recording was started by hotkey
        self._vocab_replacements = build_vocabulary_replacements(config)

        # Menu items
        self._toggle_item = rumps.MenuItem("Start Recording", callback=self._toggle_from_menu)
        mic_name = _get_input_device_name()
        self.menu = [
            self._toggle_item,
            None,  # separator
            rumps.MenuItem(f"Mic: {mic_name}", callback=None),
            rumps.MenuItem(f"Hotkey: {config['hotkey']}", callback=None),
            rumps.MenuItem(f"Model: {config['model']}", callback=None),
            None,
        ]

    def _toggle_from_menu(self, sender):
        self._toggle_recording()

    def _toggle_recording(self):
        with self._lock:
            if self._recording:
                self._stop_recording()
            else:
                self._start_recording()

    def _start_recording(self):
        self._audio_frames = []
        sr = self._transcriber.sample_rate
        self._stream = sd.InputStream(
            samplerate=sr,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()
        self._recording = True
        self.title = ICON_RECORDING
        self._toggle_item.title = "Stop Recording"

    def _stop_recording(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._recording = False
        self.title = ICON_TRANSCRIBING
        self._toggle_item.title = "Start Recording"

        # Gather audio
        if not self._audio_frames:
            self.title = ICON_IDLE
            return

        audio = np.concatenate(self._audio_frames, axis=0).flatten()
        self._audio_frames = []

        # Transcribe in background thread to keep UI responsive
        threading.Thread(target=self._transcribe_and_paste, args=(audio,), daemon=True).start()

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"Audio status: {status}")
        self._audio_frames.append(indata.copy())

    def _transcribe_and_paste(self, audio: np.ndarray):
        try:
            duration = len(audio) / self._transcriber.sample_rate
            t0 = time.time()
            text = self._transcriber.transcribe(audio)
            elapsed = time.time() - t0
            if text:
                for pattern, replacement in self._vocab_replacements:
                    text = pattern.sub(replacement, text)
                print(f"Transcribed {duration:.1f}s audio in {elapsed:.2f}s: {text}")
                _paste_and_restore(text)
            else:
                print(f"No speech detected ({duration:.1f}s audio, {elapsed:.2f}s elapsed).")
        except Exception as e:
            print(f"Transcription error: {e}")
            rumps.notification(
                "Transkeet",
                "Transcription failed",
                str(e),
            )
        finally:
            self.title = ICON_IDLE

    # ── Hotkey listener ─────────────────────────────────────────────────────

    def _start_hotkey_listener(self):
        from pynput.keyboard import Key, KeyCode, Listener

        def _canonical(key):
            """Normalize key to match our parsed set.

            Only collapses left/right variants (e.g. cmd_l → cmd) when the
            hotkey uses the generic form.  If the hotkey contains a side-
            specific key like cmd_r, that exact key is preserved.
            """
            if hasattr(key, "name"):
                name = key.name
                for suffix in ("_l", "_r"):
                    if name.endswith(suffix):
                        base = name[: -len(suffix)]
                        try:
                            generic = getattr(Key, base)
                        except AttributeError:
                            return key
                        if generic in self._hotkey_keys:
                            return generic
                        return key
                return key
            return key

        def on_press(key):
            self._pressed_keys.add(_canonical(key))
            if (
                self._hotkey_keys.issubset(self._pressed_keys)
                and not self._recording
            ):
                self._hotkey_recording = True
                with self._lock:
                    self._start_recording()

        def on_release(key):
            self._pressed_keys.discard(_canonical(key))
            if self._hotkey_recording and not self._hotkey_keys.issubset(self._pressed_keys):
                self._hotkey_recording = False
                with self._lock:
                    if self._recording:
                        self._stop_recording()

        self._listener = Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def _load_model_with_notification(self):
        try:
            self._transcriber.load()
            rumps.notification("Transkeet", "Ready", "Model loaded. Hold your hotkey to record.")
        except Exception as e:
            rumps.notification("Transkeet", "Model failed to load", str(e))

    def run(self, **kwargs):
        # Load model in background so the app launches fast
        threading.Thread(target=self._load_model_with_notification, daemon=True).start()
        self._start_hotkey_listener()
        super().run(**kwargs)


def _check_accessibility():
    """Prompt for Accessibility access if not already granted."""
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        trusted = AXIsProcessTrustedWithOptions(
            {kAXTrustedCheckOptionPrompt: True}
        )
        if not trusted:
            print("Accessibility access not yet granted — macOS should show a prompt.")
        return trusted
    except ImportError:
        print("Could not import ApplicationServices — skipping accessibility check.")
        return True


def main():
    # Accessibility check is handled by the native Mach-O launcher in the .app bundle.
    # When running from terminal, check here as a fallback.
    if not _check_accessibility():
        print("Tip: Launch via Transkeet.app for proper Accessibility permission handling.")
    config = ensure_config()
    print(f"Config: hotkey={config['hotkey']}, model={config['model']}")
    app = TranskeetApp(config)
    app.run()


if __name__ == "__main__":
    main()
