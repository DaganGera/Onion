package org.algorangers.parakh;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.webkit.GeolocationPermissions;
import android.webkit.PermissionRequest;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebChromeClient;

import java.util.ArrayList;
import java.util.List;

/**
 * Handles the WebView's camera permission ourselves.
 *
 * Capacitor's default handler asks Android for permission on every
 * getUserMedia call and answers the WebView's request from the callback. When
 * a second request (for example location) overlaps, it can answer the same
 * PermissionRequest twice, which throws "Either grant() or deny() has been
 * already called" on the main thread and kills the app. Here the Android
 * camera permission is asked once at launch, every WebView request is answered
 * exactly once, and location is never requested (it is optional in Parakh).
 */
public class MainActivity extends BridgeActivity {
    private static final int REQ_CAMERA = 4201;
    private final List<PermissionRequest> pending = new ArrayList<>();

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getBridge().getWebView().setWebChromeClient(new BridgeWebChromeClient(getBridge()) {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> handle(request));
            }

            @Override
            public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                callback.invoke(origin, hasCoarseLocation(), false);
            }
        });
        if (!hasCamera()) {
            ActivityCompat.requestPermissions(this, new String[] { Manifest.permission.CAMERA }, REQ_CAMERA);
        }
    }

    private boolean hasCamera() {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean hasCoarseLocation() {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private void handle(PermissionRequest request) {
        boolean wantsCamera = false;
        for (String r : request.getResources()) {
            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(r)) wantsCamera = true;
        }
        if (!wantsCamera) {
            answer(request, false);
            return;
        }
        if (hasCamera()) {
            answer(request, true);
            return;
        }
        synchronized (pending) {
            pending.add(request);
        }
        ActivityCompat.requestPermissions(this, new String[] { Manifest.permission.CAMERA }, REQ_CAMERA);
    }

    private void answer(PermissionRequest request, boolean grant) {
        try {
            if (grant) request.grant(new String[] { PermissionRequest.RESOURCE_VIDEO_CAPTURE });
            else request.deny();
        } catch (IllegalStateException alreadyAnswered) {
            // The WebView already has an answer; never let this crash the app.
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (requestCode != REQ_CAMERA) {
            super.onRequestPermissionsResult(requestCode, permissions, grantResults);
            return;
        }
        boolean granted = hasCamera();
        List<PermissionRequest> toAnswer;
        synchronized (pending) {
            toAnswer = new ArrayList<>(pending);
            pending.clear();
        }
        for (PermissionRequest r : toAnswer) answer(r, granted);
    }
}
