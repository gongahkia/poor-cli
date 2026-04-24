from poor_cli.voice.controller import VoiceSettings
from poor_cli.voice.preferences import VoicePreferencesStore


def test_voice_preferences_store_round_trip(tmp_path):
    store = VoicePreferencesStore(str(tmp_path))
    settings = VoiceSettings(
        enabled=True,
        conversation_mode=True,
        language="en",
        speak_responses=False,
        model_name="small",
        tts_engine="say",
        tts_rate=1.25,
        max_spoken_chars=420,
    )

    store.save(settings)
    loaded = store.load()

    assert loaded.conversation_mode is True
    assert loaded.language == "en"
    assert loaded.speak_responses is False
    assert loaded.model_name == "small"
    assert loaded.tts_engine == "say"
    assert loaded.tts_rate == 1.25
    assert loaded.max_spoken_chars == 420
