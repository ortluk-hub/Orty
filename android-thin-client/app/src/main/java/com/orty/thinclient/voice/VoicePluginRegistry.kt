package com.orty.thinclient.voice

object VoicePluginRegistry {
    var recognitionEngine: VoiceRecognitionEngine = NoOpVoiceRecognitionEngine()
    var ttsEngine: TextToSpeechEngine = NoOpTextToSpeechEngine()
}
