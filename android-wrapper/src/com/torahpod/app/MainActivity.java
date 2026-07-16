package com.torahpod.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

public class MainActivity extends Activity {
    private static final String START_URL = "https://torah-pod.pages.dev/";
    private WebView webView;
    private boolean nativeAudioReceiverRegistered = false;
    private final BroadcastReceiver nativeAudioReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (intent != null && NativeAudioService.ACTION_PROGRESS.equals(intent.getAction())) {
                forwardNativeProgress(intent);
            }
        }
    };

    @Override
    @SuppressLint("SetJavaScriptEnabled")
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestWindowFeature(Window.FEATURE_NO_TITLE);

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(247, 239, 223));
        webView.setScrollBarStyle(View.SCROLLBARS_INSIDE_OVERLAY);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setUserAgentString(settings.getUserAgentString() + " TorahPodAndroid/1");

        webView.addJavascriptInterface(new TorahPodBridge(), "TorahPodNative");
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme();
                if ("http".equals(scheme) || "https".equals(scheme)) {
                    view.loadUrl(uri.toString());
                    return true;
                }
                return false;
            }
        });

        setContentView(webView);
        registerNativeAudioReceiver();
        requestNotificationPermission();
        if (savedInstanceState == null) {
            webView.loadUrl(START_URL);
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    private void registerNativeAudioReceiver() {
        if (nativeAudioReceiverRegistered) return;
        IntentFilter filter = new IntentFilter(NativeAudioService.ACTION_PROGRESS);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(nativeAudioReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(nativeAudioReceiver, filter);
        }
        nativeAudioReceiverRegistered = true;
    }

    private void unregisterNativeAudioReceiver() {
        if (!nativeAudioReceiverRegistered) return;
        try {
            unregisterReceiver(nativeAudioReceiver);
        } catch (IllegalArgumentException ignored) {
        }
        nativeAudioReceiverRegistered = false;
    }

    private void forwardNativeProgress(Intent intent) {
        if (webView == null) return;
        try {
            JSONObject payload = new JSONObject();
            payload.put("position", intent.getIntExtra(NativeAudioService.EXTRA_POSITION, 0));
            payload.put("duration", intent.getIntExtra(NativeAudioService.EXTRA_DURATION, 0));
            payload.put("playing", intent.getBooleanExtra(NativeAudioService.EXTRA_PLAYING, false));
            String script = "window.TorahPodNativeProgress && window.TorahPodNativeProgress(" + payload.toString() + ");";
            webView.post(() -> {
                if (webView != null) {
                    webView.evaluateJavascript(script, null);
                }
            });
        } catch (Exception ignored) {
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1001);
        }
    }

    private void startAudioService(Intent intent) {
        if (Build.VERSION.SDK_INT >= 26) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
    }

    private class TorahPodBridge {
        @JavascriptInterface
        public void play(String json) {
            try {
                JSONObject payload = new JSONObject(json);
                Intent intent = new Intent(MainActivity.this, NativeAudioService.class);
                intent.setAction(NativeAudioService.ACTION_PLAY);
                intent.putExtra(NativeAudioService.EXTRA_URL, payload.optString("src"));
                intent.putExtra(NativeAudioService.EXTRA_TITLE, payload.optString("title"));
                intent.putExtra(NativeAudioService.EXTRA_SHOW, payload.optString("show"));
                intent.putExtra(NativeAudioService.EXTRA_ARTWORK, payload.optString("artwork"));
                startAudioService(intent);
            } catch (Exception ignored) {
            }
        }

        @JavascriptInterface
        public void toggle() {
            Intent intent = new Intent(MainActivity.this, NativeAudioService.class);
            intent.setAction(NativeAudioService.ACTION_TOGGLE);
            startAudioService(intent);
        }

        @JavascriptInterface
        public void stop() {
            Intent intent = new Intent(MainActivity.this, NativeAudioService.class);
            intent.setAction(NativeAudioService.ACTION_STOP);
            startService(intent);
        }

        @JavascriptInterface
        public void seekBy(int seconds) {
            Intent intent = new Intent(MainActivity.this, NativeAudioService.class);
            intent.setAction(NativeAudioService.ACTION_SEEK_BY);
            intent.putExtra(NativeAudioService.EXTRA_SECONDS, seconds);
            startService(intent);
        }

        @JavascriptInterface
        public void seekTo(int seconds) {
            Intent intent = new Intent(MainActivity.this, NativeAudioService.class);
            intent.setAction(NativeAudioService.ACTION_SEEK_TO);
            intent.putExtra(NativeAudioService.EXTRA_POSITION, seconds);
            startService(intent);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (webView != null) {
            webView.saveState(outState);
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        unregisterNativeAudioReceiver();
        if (webView != null) {
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
