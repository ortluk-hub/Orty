package com.orty.thinclient.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "orty_preferences")

class ConfigStore(private val context: Context) {
    private val baseUrlKey = stringPreferencesKey("base_url")
    private val secretKey = stringPreferencesKey("secret")

    val configFlow: Flow<OrtyConfig> = context.dataStore.data.map { prefs ->
        OrtyConfig(
            baseUrl = prefs[baseUrlKey] ?: "http://192.168.12.175:8080",
            secret = prefs[secretKey] ?: ""
        )
    }

    suspend fun save(config: OrtyConfig) {
        context.dataStore.edit { prefs ->
            prefs[baseUrlKey] = config.baseUrl.trim().trimEnd('/')
            prefs[secretKey] = config.secret.trim()
        }
    }
}
