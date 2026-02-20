package com.orty.thinclient

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.orty.thinclient.data.ChatRepository
import com.orty.thinclient.data.ConfigStore
import com.orty.thinclient.ui.ChatScreen
import com.orty.thinclient.ui.CommandCenterScreen
import com.orty.thinclient.ui.SettingsScreen
import com.orty.thinclient.ui.theme.OrtyTheme
import com.orty.thinclient.viewmodel.ChatViewModel
import com.orty.thinclient.voice.AndroidTextToSpeechEngine
import com.orty.thinclient.voice.NoOpVoiceRecognitionEngine

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val repository = ChatRepository()
        val configStore = ConfigStore(applicationContext)
        val ttsEngine = AndroidTextToSpeechEngine(applicationContext)
        val voiceEngine = NoOpVoiceRecognitionEngine()

        setContent {
            OrtyTheme {
                val navController = rememberNavController()

                val vm: ChatViewModel = viewModel(
                    factory = ChatViewModel.factory(repository, configStore, voiceEngine, ttsEngine)
                )

                // ✅ Critical fix: subscribe Compose to uiState updates (StateFlow -> Compose State)
                val state = vm.uiState.collectAsStateWithLifecycle().value

                NavHost(navController = navController, startDestination = "chat") {
                    composable("chat") {
                        ChatScreen(
                            state = state,
                            onInputChanged = vm::onInputChanged,
                            onSend = vm::sendMessage,
                            onSettings = { navController.navigate("settings") },
                            onCommands = { navController.navigate("commands") },
                            onVoiceInput = vm::startVoiceInput,
                            onStopVoice = vm::stopVoiceInput,
                            onErrorConsumed = vm::clearError
                        )
                    }
                    composable("commands") {
                        CommandCenterScreen(
                            selectedCommand = state.selectedCommand,
                            input = state.input,
                            onBack = { navController.popBackStack() },
                            onSelectCommand = vm::setSelectedCommand,
                            onInputChanged = vm::onInputChanged,
                            onExecute = vm::sendMessage
                        )
                    }
                    composable("settings") {
                        SettingsScreen(
                            config = state.config,
                            onSave = vm::saveConfig,
                            onBack = { navController.popBackStack() }
                        )
                    }
                }
            }
        }
    }
}
