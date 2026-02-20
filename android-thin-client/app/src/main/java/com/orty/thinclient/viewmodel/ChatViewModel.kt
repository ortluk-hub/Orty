package com.orty.thinclient.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.orty.thinclient.data.AssistantCommand
import com.orty.thinclient.data.AssistantCommandType
import com.orty.thinclient.data.ChatMessage
import com.orty.thinclient.data.ChatRepository
import com.orty.thinclient.data.ConfigStore
import com.orty.thinclient.data.OrtyConfig
import com.orty.thinclient.voice.TextToSpeechEngine
import com.orty.thinclient.voice.VoiceRecognitionEngine
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ChatUiState(
    val messages: List<ChatMessage> = emptyList(),
    val input: String = "",
    val isLoading: Boolean = false,
    val error: String? = null,
    val config: OrtyConfig = OrtyConfig(),
    val conversationId: String? = null,
    val selectedCommand: AssistantCommandType = AssistantCommandType.CHAT,
    val isListening: Boolean = false
)

class ChatViewModel(
    private val repository: ChatRepository,
    private val configStore: ConfigStore,
    private val voiceRecognitionEngine: VoiceRecognitionEngine,
    private val textToSpeechEngine: TextToSpeechEngine
) : ViewModel() {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            configStore.configFlow.collect { cfg ->
                _uiState.update { it.copy(config = cfg) }
            }
        }
    }

    fun onInputChanged(value: String) {
        _uiState.update { it.copy(input = value) }
    }

    fun setSelectedCommand(type: AssistantCommandType) {
        _uiState.update { it.copy(selectedCommand = type) }
    }

    fun startVoiceInput() {
        _uiState.update { it.copy(isListening = true) }
        voiceRecognitionEngine.startListening(
            onResult = { text ->
                _uiState.update { it.copy(input = text, isListening = false) }
            },
            onError = { message ->
                _uiState.update { it.copy(error = message, isListening = false) }
            }
        )
    }

    fun stopVoiceInput() {
        voiceRecognitionEngine.stopListening()
        _uiState.update { it.copy(isListening = false) }
    }

    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    fun saveConfig(baseUrl: String, secret: String) {
        viewModelScope.launch {
            configStore.save(OrtyConfig(baseUrl = baseUrl, secret = secret))
        }
    }

    fun sendMessage() {
        val current = _uiState.value
        val outgoing = current.input.trim()
        if (outgoing.isBlank() || current.isLoading) return

        if (current.selectedCommand == AssistantCommandType.CHAT) {
            sendChatMessage(outgoing)
            return
        }

        executeCommand(current.selectedCommand, outgoing)
    }

    fun executeCommand(type: AssistantCommandType, utterance: String) {
        val current = _uiState.value
        if (utterance.isBlank() || current.isLoading) return

        _uiState.update {
            it.copy(
                messages = it.messages + ChatMessage("${type.name.lowercase()}: $utterance", isUser = true),
                input = "",
                isLoading = true,
                error = null,
                selectedCommand = type
            )
        }

        viewModelScope.launch {
            val result = repository.executeAssistantCommand(current.config, AssistantCommand(type, utterance))
            result.onSuccess { response ->
                _uiState.update {
                    it.copy(
                        messages = it.messages + ChatMessage(response.message, isUser = false),
                        isLoading = false
                    )
                }
                textToSpeechEngine.speak(response.message)
            }.onFailure { throwable ->
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        error = throwable.message ?: "Unexpected error"
                    )
                }
            }
        }
    }

    private fun sendChatMessage(outgoing: String) {
        _uiState.update {
            it.copy(
                messages = it.messages + ChatMessage(outgoing, isUser = true),
                input = "",
                isLoading = true,
                error = null
            )
        }

        viewModelScope.launch {
            val result = repository.sendMessage(_uiState.value.config, outgoing)
            result.onSuccess { response ->
                _uiState.update {
                    it.copy(
                        messages = it.messages + ChatMessage(response.reply, isUser = false),
                        conversationId = response.conversation_id,
                        isLoading = false
                    )
                }
                textToSpeechEngine.speak(response.reply)
            }.onFailure { throwable ->
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        error = throwable.message ?: "Unexpected error"
                    )
                }
            }
        }
    }

    companion object {
        fun factory(
            repository: ChatRepository,
            configStore: ConfigStore,
            voiceRecognitionEngine: VoiceRecognitionEngine,
            textToSpeechEngine: TextToSpeechEngine
        ): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T {
                    return ChatViewModel(
                        repository,
                        configStore,
                        voiceRecognitionEngine,
                        textToSpeechEngine
                    ) as T
                }
            }
    }
}
