package com.orty.thinclient.data

data class ChatRequest(
    val message: String
)

data class ChatResponse(
    val reply: String,
    val conversation_id: String
)

enum class AssistantCommandType {
    CHAT,
    TASK,
    REMINDER,
    ALARM,
    TIMER
}

data class AssistantCommandRequest(
    val type: String,
    val utterance: String
)

data class AssistantCommandResponse(
    val status: String,
    val message: String
)

data class AssistantCommand(
    val type: AssistantCommandType,
    val utterance: String
)

data class ChatMessage(
    val text: String,
    val isUser: Boolean
)

data class OrtyConfig(
    val baseUrl: String = "http://192.168.12.175:8080",
    val secret: String = ""
)
