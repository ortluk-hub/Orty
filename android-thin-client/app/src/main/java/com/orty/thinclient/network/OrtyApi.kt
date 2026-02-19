package com.orty.thinclient.network

import com.orty.thinclient.data.ChatRequest
import com.orty.thinclient.data.ChatResponse
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST

interface OrtyApi {
    @POST("/chat")
    suspend fun chat(
        @Header("x-orty-secret") secret: String,
        @Body request: ChatRequest
    ): ChatResponse
}
