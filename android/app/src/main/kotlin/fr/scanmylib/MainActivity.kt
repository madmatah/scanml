package fr.scanmylib

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.navigation.compose.rememberNavController
import fr.scanmylib.diagnostics.CrashReportDialog
import fr.scanmylib.diagnostics.CrashReporter
import fr.scanmylib.ui.ScanMyLibNavHost
import fr.scanmylib.ui.theme.ScanMyLibTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val settings = (application as ScanMyLibApplication).container.settings
        setContent {
            ScanMyLibTheme {
                Surface(Modifier.fillMaxSize()) {
                    val navController = rememberNavController()
                    // The start screen depends on the pairing, read once (a few milliseconds).
                    val paired by produceState<Boolean?>(initialValue = null) {
                        value = settings.current().server != null
                    }
                    paired?.let { ScanMyLibNavHost(navController, paired = it) }
                    var crashReport by remember { mutableStateOf(CrashReporter.lastCrash(this@MainActivity)) }
                    crashReport?.let { report ->
                        CrashReportDialog(report) {
                            CrashReporter.clear(this@MainActivity)
                            crashReport = null
                        }
                    }
                }
            }
        }
    }
}
