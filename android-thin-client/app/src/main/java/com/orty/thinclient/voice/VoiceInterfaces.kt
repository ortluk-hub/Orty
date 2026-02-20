package com.orty.thinclient.voice

interface VoiceRecognitionEngine {
    fun startListening(onResult: (String) -> Unit, onError: (String) -> Unit)
    fun stopListening()
}

interface TextToSpeechEngine {
    fun speak(text: String)
    fun stop()
}

class NoOpVoiceRecognitionEngine : VoiceRecognitionEngine {
    override fun startListening(onResult: (String) -> Unit, onError: (String) -> Unit) {
        onError("Voice recognition plugin not configured.")
    }

    override fun stopListening() = Unit
}

class NoOpTextToSpeechEngine : TextToSpeechEngine {
    override fun speak(text: String) = Unit
    override fun stop() = Unit
}
