package com.orty.thinclient.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.orty.thinclient.data.ChatMessage
import com.orty.thinclient.data.ChatRepository
import com.orty.thinclient.data.ConfigStore
import com.orty.thinclient.data.OrtyConfig
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
    val conversationId: String? = null
)

class ChatViewModel(
    private val repository: ChatRepository,
    private val configStore: ConfigStore
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
        fun factory(repository: ChatRepository, configStore: ConfigStore): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T {
                    return ChatViewModel(repository, configStore) as T
                }
            }
    }
}
