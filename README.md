# Transkeet 🦜

Push-to-talk voice transcription for your macOS menu bar, powered by [Parakeet TDT](https://github.com/ml-explore/mlx-examples) running locally on Apple Silicon via MLX.

Hold a hotkey, speak, release — your words appear at the cursor. No cloud, no API calls, everything stays on your machine.

## Requirements

- macOS on Apple Silicon (M1+)
- Python 3.10+
- [ffmpeg](https://formulae.brew.sh/formula/ffmpeg) (used by the transcription engine)
- A [Hugging Face](https://huggingface.co) account with an access token (to download the model)
- Microphone access (macOS will prompt on first use)
- Accessibility access for keyboard listening and simulated paste
  (System Settings → Privacy & Security → Accessibility)

## Setup

```bash
# Install ffmpeg if you don't have it
brew install ffmpeg

# Set your Hugging Face token (add this to your shell profile to persist it)
export HF_TOKEN="hf_..."

# Create a virtualenv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Build the .app bundle
python setup.py
```

### Setup with Devbox (alternative)

If you have [`devbox`](https://www.jetify.com/devbox), simply continue to the next step.

## Usage

The recommended way to run Transkeet is via the `.app` bundle:

```bash
open dist/Transkeet.app
```

The `.app` bundle embeds Python inside a native macOS binary, which means macOS can properly grant and remember Accessibility, Input Monitoring, and Microphone permissions.

On first launch macOS will prompt you to grant Accessibility and Input Monitoring access — look for **Transkeet** in System Settings → Privacy & Security and toggle it on. The Parakeet model (~2.5 GB) will also be downloaded from Hugging Face and cached locally.

A 🦜 appears in your menu bar. Hold **Right Cmd** (default) to record — the icon turns 🔴 while listening. Release the key and it switches to 🔄 while transcribing, then pastes the result at your cursor and returns to 🦜.

The menu bar dropdown shows your active microphone, current hotkey, and model.

### Start at login

To launch Transkeet automatically when you log in, create a macOS Launch Agent:

```bash
cat > ~/Library/LaunchAgents/com.arkham.transkeet.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.arkham.transkeet</string>
    <key>ProgramArguments</key>
    <array>
        <string>TRANSKEET_PATH/dist/Transkeet.app/Contents/MacOS/Transkeet</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/transkeet.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/transkeet.stderr.log</string>
</dict>
</plist>
EOF

launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.arkham.transkeet.plist
```

> **Note:** Replace `TRANSKEET_PATH` with the absolute path to your clone (e.g. `/Users/you/code/transkeet`).

To stop or remove the launch agent:

```bash
# Stop the agent
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.arkham.transkeet.plist

# Remove it entirely
rm ~/Library/LaunchAgents/com.arkham.transkeet.plist
```

Logs are written to `/tmp/transkeet.stdout.log` and `/tmp/transkeet.stderr.log`.

### Running from the terminal

You can also run Transkeet directly from your terminal if you prefer:

```bash
source .venv/bin/activate
transkeet

# or with devbox:
devbox run start
```

This works for quick testing but has a downside: macOS attributes permissions to your terminal app (e.g. Terminal.app or iTerm2) rather than to Transkeet itself. If you use this approach, you'll need to grant Accessibility access to your terminal.

## Configuration

Config lives at `~/.config/transkeet/config.jsonc` (created on first run):

```jsonc
{
  // Hotkey to hold for push-to-talk recording.
  // Format: modifier+modifier+key  (single key also works)
  // Available modifiers: cmd, shift, ctrl, alt
  // Side-specific variants: cmd_r, cmd_l, shift_r, shift_l, ctrl_r, ctrl_l, alt_r, alt_l
  "hotkey": "cmd_r",

  // Parakeet model identifier (any parakeet-mlx compatible model).
  "model": "mlx-community/parakeet-tdt-0.6b-v3",
}
```

## How it works

1. A global keyboard listener (pynput) watches for your hotkey
2. While held, audio is captured from the default mic at 16 kHz (sounddevice)
3. On release, the audio is transcribed locally with Parakeet TDT on MLX
4. The transcribed text is placed on the clipboard and pasted via simulated Cmd+V
5. Your original clipboard contents are restored afterward
