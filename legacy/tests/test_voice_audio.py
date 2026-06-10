import math

from poor_cli.voice.audio import (
    RecordedAudio,
    VoiceActivityDetector,
    VadResult,
    apply_vad_stop_heuristics_with_config,
    resample_audio,
)


def test_resample_passthrough_16khz():
    samples = [
        math.sin(index / 16000.0 * 440.0 * math.tau)
        for index in range(16000)
    ]
    result = resample_audio(samples, 16000, 16000)
    assert len(result) == 16000


def test_vad_silence_timeout():
    detector = VoiceActivityDetector(0.01, 1500)
    silence = [0.0] * 480
    for _ in range(49):
        assert detector.process_frame(silence, 16000) != VadResult.SILENCE_TIMEOUT
    assert detector.process_frame(silence, 16000) == VadResult.SILENCE_TIMEOUT


def test_vad_stop_heuristics_trim_trailing_silence():
    speech = [
        math.sin(index / 16000.0 * 220.0 * math.tau) * 0.4
        for index in range(9600)
    ]
    samples = speech + ([0.0] * 32000)
    processed = apply_vad_stop_heuristics_with_config(
        RecordedAudio(samples=samples, sample_rate=16000),
        speech_threshold=0.01,
        silence_duration_ms=1500,
        speech_padding_ms=150,
    )
    assert processed.samples
    assert len(processed.samples) < len(samples)
    assert len(processed.samples) >= len(speech)


def test_vad_stop_heuristics_drop_silence_only_capture():
    processed = apply_vad_stop_heuristics_with_config(
        RecordedAudio(samples=[0.0] * 32000, sample_rate=16000),
        speech_threshold=0.01,
        silence_duration_ms=1500,
        speech_padding_ms=150,
    )
    assert processed.samples == []
