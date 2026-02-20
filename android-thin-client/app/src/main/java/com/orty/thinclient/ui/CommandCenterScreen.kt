package com.orty.thinclient.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.orty.thinclient.data.AssistantCommandType

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CommandCenterScreen(
    selectedCommand: AssistantCommandType,
    input: String,
    onBack: () -> Unit,
    onSelectCommand: (AssistantCommandType) -> Unit,
    onInputChanged: (String) -> Unit,
    onExecute: () -> Unit
) {
    val commandTypes = listOf(
        AssistantCommandType.CHAT,
        AssistantCommandType.TASK,
        AssistantCommandType.REMINDER,
        AssistantCommandType.ALARM,
        AssistantCommandType.TIMER
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Assistant Command Center") },
                navigationIcon = {
                    TextButton(onClick = onBack) {
                        Text("Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                contentPadding = PaddingValues(4.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                items(commandTypes) { commandType ->
                    Card(onClick = { onSelectCommand(commandType) }) {
                        Text(
                            text = commandType.name.lowercase().replaceFirstChar { it.uppercase() },
                            modifier = Modifier.padding(16.dp)
                        )
                        if (selectedCommand == commandType) {
                            Text("Selected", modifier = Modifier.padding(start = 16.dp, bottom = 16.dp))
                        }
                    }
                }
            }

            OutlinedTextField(
                value = input,
                onValueChange = onInputChanged,
                label = { Text("What should Orty do?") },
                modifier = Modifier.fillMaxWidth()
            )

            Button(onClick = onExecute, modifier = Modifier.fillMaxWidth()) {
                Text("Run ${selectedCommand.name.lowercase()} command")
            }
        }
    }
}
