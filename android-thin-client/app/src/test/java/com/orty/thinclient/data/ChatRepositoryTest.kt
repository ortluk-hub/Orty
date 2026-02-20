package com.orty.thinclient.data

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ChatRepositoryTest {
    private lateinit var server: MockWebServer
    private val repository = ChatRepository()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun sendMessage_returnsReplyOnSuccess() = runBlocking {
        server.enqueue(
            MockResponse().setBody("{\"reply\":\"hello\",\"conversation_id\":\"123\"}")
                .setResponseCode(200)
        )

        val config = OrtyConfig(baseUrl = server.url("/").toString(), secret = "abc")
        val result = repository.sendMessage(config, "hi")

        assertTrue(result.isSuccess)
        assertEquals("hello", result.getOrNull()?.reply)
        assertEquals("abc", server.takeRequest().getHeader("x-orty-secret"))
    }

    @Test
    fun executeAssistantCommand_routesToSpecificCommandEndpoint() = runBlocking {
        server.enqueue(
            MockResponse().setBody("{\"status\":\"ok\",\"message\":\"alarm set\"}")
                .setResponseCode(200)
        )

        val config = OrtyConfig(baseUrl = server.url("/").toString(), secret = "abc")
        val result = repository.executeAssistantCommand(
            config,
            AssistantCommand(AssistantCommandType.ALARM, "set alarm for 7am")
        )

        val request = server.takeRequest()
        assertTrue(result.isSuccess)
        assertEquals("/assistant/alarm", request.path)
        assertEquals("abc", request.getHeader("x-orty-secret"))
        assertEquals("alarm set", result.getOrNull()?.message)
    }
}
