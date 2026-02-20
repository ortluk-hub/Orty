package com.orty.thinclient.network

import com.orty.thinclient.data.AssistantCommandRequest
import com.orty.thinclient.data.AssistantCommandResponse
import com.orty.thinclient.data.ChatRequest
import com.orty.thinclient.data.ChatResponse
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

interface OrtyApi {
    @POST("/chat")
    suspend fun chat(
        @Header("x-orty-secret") secret: String,
        @Body request: ChatRequest
    ): ChatResponse

    @POST("/assistant/{command}")
    suspend fun executeAssistantCommand(
        @Header("x-orty-secret") secret: String,
        @Path("command") command: String,
        @Body request: AssistantCommandRequest
    ): AssistantCommandResponse
}
