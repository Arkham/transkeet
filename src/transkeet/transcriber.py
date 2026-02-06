import os
import tempfile
import wave

import numpy as np


class Transcriber:
    """Lazy-loading wrapper around parakeet-mlx."""

    def __init__(self, model_id: str):
        self._model_id = model_id
        self._model = None

    def load(self):
        """Load the model (call once at startup or on first use)."""
        if self._model is not None:
            return
        from parakeet_mlx import from_pretrained

        print(f"Loading model {self._model_id} ...")
        self._model = from_pretrained(self._model_id)
        print("Model loaded.")

    @property
    def sample_rate(self) -> int:
        """Expected sample rate for the model (always 16000)."""
        return 16000

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a 1-D float32 numpy array of audio samples at 16kHz.

        Returns the transcribed text (empty string if nothing detected).
        """
        if self._model is None:
            self.load()

        if audio.ndim != 1:
            raise ValueError(f"Expected 1-D audio array, got shape {audio.shape}")

        # Ensure float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Skip very short audio (< 0.3s)
        if len(audio) < self.sample_rate * 0.3:
            return ""

        # parakeet-mlx transcribe() expects a file path, so write a temp WAV
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            self._write_wav(tmp_path, audio)
            result = self._model.transcribe(tmp_path)
            return result.text.strip()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _write_wav(self, path: str, audio: np.ndarray):
        """Write float32 mono audio to a 16-bit PCM WAV file."""
        # Convert float32 [-1.0, 1.0] → int16
        pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm.tobytes())
