package fr.scanmylib.ui.capture

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.content.res.Resources
import android.media.MediaActionSound
import android.net.Uri
import android.provider.Settings
import android.util.Log
import androidx.activity.compose.BackHandler
import androidx.activity.compose.LocalActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.StringRes
import androidx.camera.core.CameraInfo
import androidx.camera.core.CameraSelector
import androidx.camera.core.CameraState
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.view.CameraController
import androidx.camera.view.LifecycleCameraController
import androidx.camera.view.PreviewView
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.Observer
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import coil3.compose.AsyncImage
import fr.scanmylib.R
import fr.scanmylib.library.StagedPage
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.components.LocalImage
import fr.scanmylib.ui.theme.LightSystemBarIcons
import fr.scanmylib.ui.theme.ScanMyLibTheme
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Takes the photos of a run with the phone's camera, one page after the other. The photos are the
 * camera's own JPEG files at full resolution, without any retouching; they wait on the phone
 * until the user sends them from the document screen.
 */
@Composable
fun CaptureScreen(
    /**
     * Closes the camera, saying whether this visit kept photos, which then wait in the run, and
     * returns whether it closed.
     */
    onClose: (werePhotosKept: Boolean) -> Boolean,
    /** Closes the camera, keeping this visit's photos, for another source on the same run. */
    onSwitchSource: (ScanSource) -> Unit,
    viewModel: CaptureViewModel = viewModel(factory = CaptureViewModel.Factory),
) {
    // Dark whatever the system theme: the controls sit on the camera preview.
    ScanMyLibTheme(dark = true) {
        Surface(color = Color.Black, contentColor = Color.White, modifier = Modifier.fillMaxSize()) {
            LightSystemBarIcons()
            val context = LocalContext.current
            val activity = LocalActivity.current
            var granted by remember { mutableStateOf(context.hasCameraPermission()) }
            var deniedForGood by rememberSaveable { mutableStateOf(false) }
            val requestPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
                granted = it
                // Refused, and the system may not ask again: the app settings can still grant it.
                // (A permission dialog dismissed without an answer reads the same: see
                // CameraPermissionRequest.)
                deniedForGood = !it && activity != null &&
                    !ActivityCompat.shouldShowRequestPermissionRationale(activity, Manifest.permission.CAMERA)
            }
            // Back from the app settings, where the permission may have been granted.
            LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { granted = context.hasCameraPermission() }

            if (granted) {
                CameraCapture(viewModel, onClose, onSwitchSource)
            } else {
                CameraPermissionRequest(
                    deniedForGood = deniedForGood,
                    onRequest = { requestPermission.launch(Manifest.permission.CAMERA) },
                    onOpenSettings = context::openAppSettings,
                    onClose = { onClose(false) },
                )
            }
        }
    }
}

@Composable
private fun CameraCapture(
    viewModel: CaptureViewModel,
    onClose: (werePhotosKept: Boolean) -> Boolean,
    onSwitchSource: (ScanSource) -> Unit,
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val resources = LocalResources.current
    val snackbarHostState = remember { SnackbarHostState() }
    val haptics = LocalHapticFeedback.current
    val animationsOff = remember(context) { context.animationsOff() }
    CameraCloseEffect(state.closing, onClose = onClose, onCloseHandled = viewModel::onCloseHandled)
    LaunchedEffect(viewModel) {
        viewModel.messages.collect {
            if (it != CaptureMessage.PhotosNotDeleted) haptics.performHapticFeedback(HapticFeedbackType.Reject)
            // A photo not taken is a page missing: the message stays long enough to be noticed.
            snackbarHostState.showSnackbar(
                it.text(resources),
                withDismissAction = true,
                duration = SnackbarDuration.Long,
            )
        }
    }
    KeepScreenOn()
    // A rotation recreates the screen, which closes the camera: the photo being saved would be lost.
    LockOrientation(locked = state.shooting)

    // A new controller for each attempt to open the camera ("Retry").
    var attempt by rememberSaveable { mutableIntStateOf(0) }
    val camera = remember(context, attempt) { newCameraController(context) }
    val previewView = remember(context) {
        PreviewView(context).apply {
            // A TextureView: composes with the controls and the screen transitions.
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            // The whole picture, as it will be saved.
            scaleType = PreviewView.ScaleType.FIT_CENTER
            setBackgroundColor(android.graphics.Color.BLACK)
        }
    }
    var streaming by remember { mutableStateOf(false) }
    var hasFlash by remember { mutableStateOf(false) }
    var cameraFailed by remember(camera) { mutableStateOf(false) }
    DisposableEffect(camera, lifecycleOwner) {
        previewView.controller = camera
        camera.bindToLifecycle(lifecycleOwner)
        val mainExecutor = ContextCompat.getMainExecutor(context)
        val initialization = camera.initializationFuture
        initialization.addListener(
            {
                cameraFailed = try {
                    initialization.get()
                    !camera.hasCamera(CameraSelector.DEFAULT_BACK_CAMERA)
                } catch (e: Exception) {
                    Log.w(TAG, "camera unavailable", e)
                    true
                }
            },
            mainExecutor,
        )
        val streamObserver = Observer<PreviewView.StreamState> { stream ->
            streaming = stream == PreviewView.StreamState.STREAMING
            if (streaming) hasFlash = camera.cameraInfo?.hasFlashUnit() == true
        }
        previewView.previewStreamState.observe(lifecycleOwner, streamObserver)
        onDispose {
            previewView.previewStreamState.removeObserver(streamObserver)
            // No camera.unbind(): it unbinds every camera use case of the app, those of a camera
            // screen opened meanwhile included. The preview view unbinds this controller's use
            // cases when it leaves the window, and the screen's lifecycle closes the camera.
        }
    }
    // Errors once the camera is bound (in use by another app, disabled by a policy...): without
    // them, the preview would just stay black.
    var cameraUnavailable by remember(camera) { mutableStateOf(false) }
    LaunchedEffect(camera, lifecycleOwner) {
        // The camera's state can be observed once it is bound, shortly after its initialization.
        var info = camera.cameraInfo
        while (info == null) {
            delay(CAMERA_INFO_POLL_MS)
            info = camera.cameraInfo
        }
        val cameraState = info.cameraState
        val stateObserver = Observer<CameraState> { cameraUnavailable = it.error != null }
        cameraState.observe(lifecycleOwner, stateObserver)
        try {
            awaitCancellation()
        } finally {
            cameraState.removeObserver(stateObserver)
        }
    }
    LaunchedEffect(camera, state.flash) {
        camera.imageCaptureFlashMode = state.flash.imageCaptureMode
    }

    // Some countries require the shutter sound; otherwise the capture is silent.
    val shutterSound = remember {
        if (CameraInfo.mustPlayShutterSound()) {
            MediaActionSound().apply { load(MediaActionSound.SHUTTER_CLICK) }
        } else {
            null
        }
    }
    DisposableEffect(shutterSound) { onDispose { shutterSound?.release() } }
    // A short dip of the preview to dark on each shot: a white flash is harsh in a dim room.
    val shutterDip = remember { Animatable(0f) }
    val scope = rememberCoroutineScope()
    // Each photo that joins the visit: a "saved" haptic, and its thumbnail pops.
    val thumbnailScale = remember { Animatable(1f) }
    var photosSeen by remember { mutableIntStateOf(-1) }
    LaunchedEffect(state.ready, state.pages.size) {
        if (!state.ready) return@LaunchedEffect
        val photos = state.pages.size
        if (photosSeen >= 0 && photos > photosSeen) {
            haptics.performHapticFeedback(HapticFeedbackType.Confirm)
            if (!animationsOff) {
                thumbnailScale.animateTo(THUMBNAIL_POP_SCALE, tween(THUMBNAIL_POP_MS / 2))
                thumbnailScale.animateTo(1f, tween(THUMBNAIL_POP_MS / 2))
            }
        }
        photosSeen = photos
    }
    val takePhoto = {
        val started = viewModel.shoot { shot ->
            camera.takePicture(
                ImageCapture.OutputFileOptions.Builder(shot.file).build(),
                ContextCompat.getMainExecutor(context),
                object : ImageCapture.OnImageSavedCallback {
                    override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                        viewModel.onShotSaved(shot)
                    }

                    override fun onError(exception: ImageCaptureException) {
                        viewModel.onShotFailed(shot, exception)
                    }
                },
            )
        }
        if (started) {
            haptics.performHapticFeedback(HapticFeedbackType.VirtualKey)
            shutterSound?.play(MediaActionSound.SHUTTER_CLICK)
            if (!animationsOff) {
                scope.launch {
                    shutterDip.snapTo(SHUTTER_DIP_ALPHA)
                    shutterDip.animateTo(0f, tween(SHUTTER_DIP_MS))
                }
            }
        }
    }

    var leaving by rememberSaveable { mutableStateOf(false) }
    // The photo shown large, by file: a photo landing meanwhile does not take its place.
    var shownPhoto by rememberSaveable { mutableStateOf<String?>(null) }

    // Photos taken in this visit, or on their way: leaving asks first, and waits for the one being
    // saved. The pages from before the visit are not this screen's: with no photo of its own, it
    // closes at once.
    fun close() {
        if (state.photoCount == 0) onClose(false) else leaving = true
    }
    BackHandler(enabled = state.photoCount > 0) { leaving = true }

    Box(Modifier.fillMaxSize()) {
        AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize())
        Box(
            Modifier
                .fillMaxSize()
                .graphicsLayer { alpha = shutterDip.value }
                .background(Color.Black),
        )
        val problem = when {
            cameraFailed -> R.string.capture_camera_unavailable
            cameraUnavailable && !streaming -> R.string.capture_camera_busy
            else -> null
        }
        if (problem != null) {
            CameraProblem(
                problem,
                onRetry = {
                    // Lets go of the failed camera first: this screen is the only one using it.
                    camera.unbind()
                    attempt++
                },
                // This visit's photos are in the run already: the other source adds to them.
                onSwitchSource = onSwitchSource,
                modifier = Modifier.align(Alignment.Center),
            )
        } else if (state.finishing) {
            SavingLastPhoto(Modifier.align(Alignment.Center))
        }

        val closeButton = @Composable { modifier: Modifier ->
            IconButton(onClick = ::close, modifier = modifier) {
                Icon(painterResource(R.drawable.ic_close), contentDescription = stringResource(R.string.close))
            }
        }
        val counter = @Composable { modifier: Modifier -> PageCounter(state.pages.size, state.waiting, modifier) }
        val flashButton = @Composable { modifier: Modifier ->
            if (hasFlash) FlashButton(state.flash, onClick = viewModel::cycleFlash, modifier = modifier)
        }
        val lastPhoto = @Composable { modifier: Modifier ->
            // Not while a photo is being saved: it would land behind the dialog, and only the last
            // photo can be deleted, so that the one taken again keeps its place. Only this visit's
            // photos are shown: the pages from before it are not this screen's to delete.
            LastPhoto(
                state.pages.lastOrNull(),
                enabled = !state.shooting,
                onClick = { shownPhoto = it.file.path },
                modifier = modifier.graphicsLayer {
                    scaleX = thumbnailScale.value
                    scaleY = thumbnailScale.value
                },
            )
        }
        val shutter = @Composable { modifier: Modifier ->
            ShutterButton(
                enabled = streaming && state.ready && !state.shooting && !state.finishing,
                saving = state.shooting,
                onClick = takePhoto,
                modifier = modifier,
            )
        }
        val done = @Composable { modifier: Modifier ->
            // Also while a photo is being saved: the screen then closes once it has joined the run.
            FilledTonalButton(
                onClick = viewModel::finish,
                enabled = state.photoCount > 0 && !state.finishing,
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                modifier = modifier,
            ) {
                Text(stringResource(R.string.capture_done), maxLines = 1)
            }
        }
        val insets = WindowInsets.safeDrawing
        if (LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE) {
            Box(
                Modifier
                    .align(Alignment.CenterStart)
                    .fillMaxHeight()
                    .windowInsetsPadding(insets.only(WindowInsetsSides.Vertical + WindowInsetsSides.Start))
                    .padding(8.dp),
            ) {
                closeButton(Modifier.align(Alignment.TopCenter))
                counter(Modifier.align(Alignment.Center))
                flashButton(Modifier.align(Alignment.BottomCenter))
            }
            // The shutter in the middle, whatever the size of the other controls.
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier
                    .align(Alignment.CenterEnd)
                    .fillMaxHeight()
                    .windowInsetsPadding(insets.only(WindowInsetsSides.Vertical + WindowInsetsSides.End))
                    .padding(16.dp),
            ) {
                Box(Modifier.weight(1f), contentAlignment = Alignment.TopCenter) { done(Modifier) }
                shutter(Modifier.padding(vertical = 12.dp))
                Box(Modifier.weight(1f), contentAlignment = Alignment.BottomCenter) { lastPhoto(Modifier) }
            }
        } else {
            Box(
                Modifier
                    .align(Alignment.TopCenter)
                    .fillMaxWidth()
                    .windowInsetsPadding(insets.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal))
                    .padding(8.dp),
            ) {
                closeButton(Modifier.align(Alignment.CenterStart))
                counter(Modifier.align(Alignment.Center))
                flashButton(Modifier.align(Alignment.CenterEnd))
            }
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .windowInsetsPadding(insets.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal))
                    .padding(horizontal = 12.dp, vertical = 24.dp),
            ) {
                Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) { lastPhoto(Modifier) }
                shutter(Modifier.padding(horizontal = 8.dp))
                Box(Modifier.weight(1f), contentAlignment = Alignment.CenterEnd) { done(Modifier) }
            }
        }
        SnackbarHost(
            snackbarHostState,
            Modifier
                .align(Alignment.BottomCenter)
                .windowInsetsPadding(insets)
                .padding(bottom = 120.dp),
        )
    }

    // Nothing left to keep (the only photo failed): nothing to ask. Not before the visit is known:
    // a dialog restored with the screen would close before its photos are read.
    val nothingToKeep = state.ready && state.photoCount == 0
    LaunchedEffect(nothingToKeep) { if (nothingToKeep) leaving = false }
    if (leaving && state.photoCount > 0) {
        LeaveDialog(
            count = state.photoCount,
            waiting = state.waiting,
            onKeep = {
                leaving = false
                viewModel.finish()
            },
            onDiscard = {
                leaving = false
                viewModel.discard()
            },
            onDismiss = { leaving = false },
        )
    }
    state.pages.firstOrNull { it.file.path == shownPhoto }?.let { page ->
        LastPhotoDialog(
            page = page,
            onDelete = {
                shownPhoto = null
                viewModel.deletePage(page)
            },
            onDismiss = { shownPhoto = null },
        )
    }
}

private fun newCameraController(context: Context) = LifecycleCameraController(context).apply {
    // Preview and photos only: no image analysis, no video.
    setEnabledUseCases(CameraController.IMAGE_CAPTURE)
    imageCaptureMode = ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY
    // The largest photos the camera takes at a normal pace, in its native 4:3 shape.
    val fullFrame = ResolutionSelector.Builder()
        .setAspectRatioStrategy(AspectRatioStrategy.RATIO_4_3_FALLBACK_AUTO_STRATEGY)
        .setResolutionStrategy(ResolutionStrategy.HIGHEST_AVAILABLE_STRATEGY)
        .build()
    setImageCaptureResolutionSelector(fullFrame)
    // The preview in the same shape (CameraX's default for previews), whatever the screen's: on an
    // exactly 16:9 screen, the controller would make the preview 16:9, and CameraX would then crop
    // every photo to the part both show, decoding and re-encoding it.
    setPreviewResolutionSelector(fullFrame)
}

/** The shutter; while [saving] the last photo, it shows so. */
@Composable
private fun ShutterButton(enabled: Boolean, saving: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val description = stringResource(R.string.capture_shutter)
    val color = Color.White.copy(alpha = if (enabled) 1f else DISABLED_ALPHA)
    Box(
        contentAlignment = Alignment.Center,
        modifier = modifier
            .size(80.dp)
            .clip(CircleShape)
            .border(4.dp, color, CircleShape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .semantics { contentDescription = description }
            .padding(10.dp),
    ) {
        if (saving) {
            CircularProgressIndicator(color = Color.White, strokeWidth = 3.dp, modifier = Modifier.size(36.dp))
        } else {
            Box(
                Modifier
                    .fillMaxSize()
                    .clip(CircleShape)
                    .background(color),
            )
        }
    }
}

/**
 * The camera could not be opened, or another app holds it: try again, or continue with another
 * source on the same run.
 */
@Composable
private fun CameraProblem(
    @StringRes problem: Int,
    onRetry: () -> Unit,
    onSwitchSource: (ScanSource) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        verticalArrangement = Arrangement.spacedBy(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = modifier
            .widthIn(max = 320.dp)
            .padding(32.dp),
    ) {
        Icon(painterResource(R.drawable.ic_photo_camera), contentDescription = null, modifier = Modifier.size(48.dp))
        Text(stringResource(problem), style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        Text(
            stringResource(R.string.capture_problem_help),
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center,
        )
        Button(onClick = onRetry) { Text(stringResource(R.string.retry)) }
        OutlinedButton(onClick = { onSwitchSource(ScanSource.GOOGLE_SCANNER) }) {
            Text(stringResource(R.string.scan_source_google))
        }
        TextButton(onClick = { onSwitchSource(ScanSource.PHOTO_PICKER) }) {
            Text(stringResource(R.string.scan_source_picker))
        }
    }
}

/** While the screen waits for the last photo to be saved before closing. */
@Composable
private fun SavingLastPhoto(modifier: Modifier = Modifier) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier
            .clip(RoundedCornerShape(50))
            .background(Color.Black.copy(alpha = 0.6f))
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
        Text(stringResource(R.string.capture_saving_photo), style = MaterialTheme.typography.titleSmall)
    }
}

/**
 * The photos of this visit, "3 photos", followed by the pages that were already waiting in the
 * run, "· +5 en attente"; only the waiting pages before the first photo; nothing when there is
 * neither.
 */
@Composable
private fun PageCounter(photos: Int, waiting: Int, modifier: Modifier = Modifier) {
    if (photos == 0 && waiting == 0) return
    Row(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier
            .clip(RoundedCornerShape(50))
            .background(Color.Black.copy(alpha = 0.6f))
            .padding(horizontal = 16.dp, vertical = 6.dp),
    ) {
        if (photos == 0) {
            Text(
                pluralStringResource(R.plurals.capture_waiting_only, waiting, waiting),
                style = MaterialTheme.typography.titleMedium,
            )
        } else {
            Text(
                pluralStringResource(R.plurals.capture_count, photos, photos),
                style = MaterialTheme.typography.titleMedium,
            )
            if (waiting > 0) {
                Text(
                    pluralStringResource(R.plurals.capture_count_waiting, waiting, waiting),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

@Composable
private fun FlashButton(flash: FlashSetting, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val (icon, label) = when (flash) {
        FlashSetting.OFF -> R.drawable.ic_flash_off to R.string.capture_flash_off
        FlashSetting.AUTO -> R.drawable.ic_flash_auto to R.string.capture_flash_auto
        FlashSetting.ON -> R.drawable.ic_flash_on to R.string.capture_flash_on
    }
    IconButton(onClick = onClick, modifier = modifier) {
        Icon(painterResource(icon), contentDescription = stringResource(label))
    }
}

/** The last photo taken, small; tapping it shows it larger. */
@Composable
private fun LastPhoto(
    page: StagedPage?,
    enabled: Boolean,
    onClick: (StagedPage) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (page == null) return
    LocalImage(
        page.file,
        contentDescription = stringResource(R.string.capture_last_photo),
        modifier = modifier
            .size(width = 60.dp, height = 80.dp)
            .clip(RoundedCornerShape(8.dp))
            .border(2.dp, Color.White, RoundedCornerShape(8.dp))
            .clickable(enabled = enabled) { onClick(page) },
    )
}

@Composable
private fun LastPhotoDialog(page: StagedPage, onDelete: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.capture_last_photo)) },
        text = {
            AsyncImage(
                model = page.file,
                contentDescription = null,
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(PHOTO_ASPECT_RATIO),
            )
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.close)) }
        },
        dismissButton = {
            TextButton(onClick = onDelete) {
                Text(stringResource(R.string.capture_delete_photo), color = MaterialTheme.colorScheme.error)
            }
        },
    )
}

/**
 * Asks whether to keep the [count] photos of this visit. Its buttons name their scope, and the
 * [waiting] pages from before the visit are said to be safe: deleting never reaches them.
 */
@Composable
private fun LeaveDialog(count: Int, waiting: Int, onKeep: () -> Unit, onDiscard: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(pluralStringResource(R.plurals.capture_leave_title, count, count)) },
        text = if (waiting > 0) {
            { Text(pluralStringResource(R.plurals.capture_leave_waiting, waiting, waiting)) }
        } else {
            null
        },
        confirmButton = {
            TextButton(onClick = onKeep) { Text(pluralStringResource(R.plurals.capture_leave_keep, count, count)) }
        },
        dismissButton = {
            TextButton(onClick = onDiscard) {
                Text(
                    pluralStringResource(R.plurals.capture_leave_discard, count, count),
                    color = MaterialTheme.colorScheme.error,
                )
            }
        },
    )
}

/** Asks for the camera permission, saying why; or, refused for good, leads to the app settings. */
@Composable
private fun CameraPermissionRequest(
    deniedForGood: Boolean,
    onRequest: () -> Unit,
    onOpenSettings: () -> Unit,
    onClose: () -> Unit,
) {
    Column(
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier
            .fillMaxSize()
            .windowInsetsPadding(WindowInsets.safeDrawing)
            .padding(32.dp),
    ) {
        Icon(painterResource(R.drawable.ic_photo_camera), contentDescription = null, modifier = Modifier.size(48.dp))
        Spacer(Modifier.height(16.dp))
        Text(
            stringResource(R.string.capture_permission_title),
            style = MaterialTheme.typography.titleLarge,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            stringResource(
                if (deniedForGood) R.string.capture_permission_denied else R.string.capture_permission_rationale,
            ),
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(24.dp))
        if (deniedForGood) {
            Button(onClick = onOpenSettings) { Text(stringResource(R.string.capture_permission_settings)) }
            Spacer(Modifier.height(8.dp))
            // A permission dialog dismissed without an answer (Back, a tap outside) is not a
            // refusal, but reads like one: the system may still ask. If it will not, asking
            // returns at once without showing anything.
            OutlinedButton(onClick = onRequest) { Text(stringResource(R.string.capture_permission_grant)) }
        } else {
            Button(onClick = onRequest) { Text(stringResource(R.string.capture_permission_grant)) }
        }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = onClose) { Text(stringResource(R.string.back)) }
    }
}

/** Keeps the screen in its current orientation while [locked]. */
@Composable
private fun LockOrientation(locked: Boolean) {
    val activity = LocalActivity.current ?: return
    DisposableEffect(activity, locked) {
        if (!locked) return@DisposableEffect onDispose {}
        val requested = activity.requestedOrientation
        activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LOCKED
        onDispose { activity.requestedOrientation = requested }
    }
}

/** The screen stays on while photos are taken, page after page. */
@Composable
private fun KeepScreenOn() {
    val view = LocalView.current
    DisposableEffect(view) {
        view.keepScreenOn = true
        onDispose { view.keepScreenOn = false }
    }
}

/** The user turned animations off (developer options, or the accessibility setting). */
private fun Context.animationsOff(): Boolean =
    Settings.Global.getFloat(contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f

private fun Context.hasCameraPermission() =
    ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

private fun Context.openAppSettings() {
    try {
        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", packageName, null)))
    } catch (e: ActivityNotFoundException) {
        Log.w(TAG, "no app settings screen", e)
    }
}

private fun CaptureMessage.text(resources: Resources): String = when (this) {
    CaptureMessage.ShotFailed -> resources.getString(R.string.capture_shot_failed)
    CaptureMessage.ShotNotSaved -> resources.getString(R.string.capture_shot_not_saved)
    CaptureMessage.PhotosNotDeleted -> resources.getString(R.string.capture_photos_not_deleted)
}

private const val TAG = "Capture"
private const val CAMERA_INFO_POLL_MS = 200L
private const val SHUTTER_DIP_ALPHA = 0.4f
private const val SHUTTER_DIP_MS = 120
private const val THUMBNAIL_POP_SCALE = 1.08f
private const val THUMBNAIL_POP_MS = 150
private const val DISABLED_ALPHA = 0.4f

/** Photos are 4:3; upright ones are 3:4. */
private const val PHOTO_ASPECT_RATIO = 3f / 4f
