package com.orty.thinclient.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.orty.thinclient.data.OrtyConfig

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    config: OrtyConfig,
    onSave: (baseUrl: String, secret: String) -> Unit,
    onBack: () -> Unit
) {
    var baseUrl by remember(config.baseUrl) { mutableStateOf(config.baseUrl) }
    var secret by remember(config.secret) { mutableStateOf(config.secret) }

    Scaffold(
        topBar = { TopAppBar(title = { Text("Settings") }) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.Top
        ) {
            OutlinedTextField(
                value = baseUrl,
                onValueChange = { baseUrl = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Server URL") },
                singleLine = true
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = secret,
                onValueChange = { secret = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Shared Secret") },
                singleLine = true
            )
            Spacer(Modifier.height(20.dp))
            Row {
                Button(onClick = {
                    onSave(baseUrl, secret)
                    onBack()
                }) {
                    Text("Save")
                }
                Spacer(Modifier.width(8.dp))
                Button(onClick = onBack) { Text("Back") }
            }
        }
    }
}
