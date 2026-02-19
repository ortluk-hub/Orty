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
}
