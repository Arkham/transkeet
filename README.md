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
```

On first launch the Parakeet model (~600 MB) will be downloaded from Hugging Face and cached locally.

## Usage

```bash
source .venv/bin/activate
transkeet
```

A 🦜 appears in your menu bar. Hold **Right Cmd** (default) to record — the icon turns 🔴 while listening. Release the key and it switches to 🔄 while transcribing, then pastes the result at your cursor and returns to 🦜.

The menu bar dropdown shows your active microphone, current hotkey, and model.

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
  "model": "mlx-community/parakeet-tdt-0.6b-v3"
}
```

## How it works

1. A global keyboard listener (pynput) watches for your hotkey
2. While held, audio is captured from the default mic at 16 kHz (sounddevice)
3. On release, the audio is transcribed locally with Parakeet TDT on MLX
4. The transcribed text is placed on the clipboard and pasted via simulated Cmd+V
5. Your original clipboard contents are restored afterward
