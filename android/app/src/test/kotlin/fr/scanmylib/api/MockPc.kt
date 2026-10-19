package fr.scanmylib.api

import fr.scanmylib.model.ServerConfig
import mockwebserver3.MockResponse
import okhttp3.HttpUrl
import okhttp3.OkHttpClient

object MockPc {
    fun buildApi(url: HttpUrl) = ScanMyLibApi(OkHttpClient(), ServerConfig(url, ApiFixtures.TOKEN))

    fun buildResponse(code: Int, body: String): MockResponse = MockResponse.Builder().code(code).body(body).build()
}
