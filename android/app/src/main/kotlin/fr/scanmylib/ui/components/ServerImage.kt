package fr.scanmylib.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import coil3.compose.AsyncImage
import coil3.compose.LocalPlatformContext
import coil3.network.NetworkHeaders
import coil3.network.httpHeaders
import coil3.request.ImageRequest
import coil3.request.crossfade
import fr.scanmylib.api.authenticationHeaders
import fr.scanmylib.model.ServerConfig
import java.io.File

/**
 * An image served by the paired server, such as a page thumbnail, requested with the
 * authentication headers. The image loader's disk cache keeps it visible offline.
 */
@Composable
fun ServerImage(
    server: ServerConfig?,
    serverUrl: String?,
    contentDescription: String?,
    modifier: Modifier = Modifier,
) {
    val context = LocalPlatformContext.current
    val request = remember(context, server, serverUrl) {
        val url = if (server != null && serverUrl != null) server.resolve(serverUrl) else null
        ImageRequest.Builder(context)
            .data(url?.toString())
            .apply {
                if (server != null && url != null) {
                    val headers = NetworkHeaders.Builder()
                    authenticationHeaders(server).forEach { (name, value) -> headers[name] = value }
                    httpHeaders(headers.build())
                }
            }
            .crossfade(true)
            .build()
    }
    AsyncImage(
        model = request,
        contentDescription = contentDescription,
        contentScale = ContentScale.Crop,
        modifier = modifier,
    )
}

/** A scan stored on the phone. */
@Composable
fun LocalImage(file: File?, contentDescription: String?, modifier: Modifier = Modifier) {
    AsyncImage(
        model = file,
        contentDescription = contentDescription,
        contentScale = ContentScale.Crop,
        modifier = modifier,
    )
}
