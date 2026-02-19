package com.orty.thinclient

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.orty.thinclient.data.ChatRepository
import com.orty.thinclient.data.ConfigStore
import com.orty.thinclient.ui.ChatScreen
import com.orty.thinclient.ui.SettingsScreen
import com.orty.thinclient.ui.theme.OrtyTheme
import com.orty.thinclient.viewmodel.ChatViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val repository = ChatRepository()
        val configStore = ConfigStore(applicationContext)

        setContent {
            OrtyTheme {
                val navController = rememberNavController()
                val vm: ChatViewModel = viewModel(
                    factory = ChatViewModel.factory(repository, configStore)
                )

                NavHost(navController = navController, startDestination = "chat") {
                    composable("chat") {
                        val state = vm.uiState.value
                        ChatScreen(
                            state = state,
                            onInputChanged = vm::onInputChanged,
                            onSend = vm::sendMessage,
                            onSettings = { navController.navigate("settings") },
                            onErrorConsumed = vm::clearError
                        )
                    }
                    composable("settings") {
                        val state = vm.uiState.value
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
