package com.orty.thinclient.data

import com.orty.thinclient.network.NetworkClientFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException

class ChatRepository {
    suspend fun sendMessage(config: OrtyConfig, message: String): Result<ChatResponse> {
        return withContext(Dispatchers.IO) {
            if (message.isBlank()) {
                return@withContext Result.failure(IllegalArgumentException("Message cannot be empty."))
            }
            if (config.secret.isBlank()) {
                return@withContext Result.failure(IllegalStateException("Secret is required in Settings."))
            }

            try {
                val response = NetworkClientFactory.create(config.baseUrl)
                    .chat(config.secret, ChatRequest(message.trim()))
                Result.success(response)
            } catch (ioe: IOException) {
                Result.failure(IOException("Unable to reach server. Check LAN connection and URL.", ioe))
            } catch (e: Exception) {
                Result.failure(e)
            }
        }
    }
}
