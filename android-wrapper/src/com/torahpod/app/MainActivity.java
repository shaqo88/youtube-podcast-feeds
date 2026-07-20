package com.torahpod.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
import android.webkit.JsPromptResult;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;

import org.json.JSONObject;

public class MainActivity extends Activity {
    private static final String START_URL = "https://torah-pod.pages.dev/";
    private static final int PULL_REFRESH_THRESHOLD_DP = 92;
    private WebView webView;
    private TextView refreshIndicator;
    private FrameLayout startupOverlay;
    private float pullStartY = 0f;
    private boolean pullTracking = false;
    private boolean pullReady = false;
    private boolean pullRefreshing = false;
    private boolean nativeAudioReceiverRegistered = false;
    private final BroadcastReceiver nativeAudioReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (intent == null) return;
            if (NativeAudioService.ACTION_PROGRESS.equals(intent.getAction())) {
                forwardNativeProgress(intent);
            } else if (NativeAudioService.ACTION_CONTROL.equals(intent.getAction())) {
                forwardNativeControl(intent);
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

        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        }
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onJsPrompt(WebView view, String url, String message, String defaultValue, JsPromptResult result) {
                if (!"torahpod-native".equals(message) || !isTrustedPage(url) || !handleNativePrompt(defaultValue)) {
                    result.cancel();
                    return true;
                }
                result.confirm("");
                return true;
            }
        });
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                showStartupIndicator();
                if (pullRefreshing) {
                    showRefreshIndicator("Refreshing...", true);
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                hideStartupIndicator();
                finishPullRefresh();
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (!request.isForMainFrame()) return false;
                if (isTrustedPage(uri.toString())) return false;
                if ("https".equalsIgnoreCase(uri.getScheme()) || "mailto".equalsIgnoreCase(uri.getScheme())) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    } catch (Exception ignored) {
                    }
                }
                return true;
            }
        });
        setupPullToRefresh();

        FrameLayout root = new FrameLayout(this);
        root.addView(webView, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));
        refreshIndicator = createRefreshIndicator();
        root.addView(refreshIndicator);
        startupOverlay = createStartupOverlay();
        root.addView(startupOverlay);
        setContentView(root);
        registerNativeAudioReceiver();
        requestNotificationPermission();
        if (savedInstanceState == null) {
            webView.loadUrl(START_URL);
        } else {
            webView.restoreState(savedInstanceState);
            hideStartupIndicator();
        }
    }

    private FrameLayout createStartupOverlay() {
        FrameLayout overlay = new FrameLayout(this);
        overlay.setClickable(true);
        overlay.setFocusable(true);
        overlay.setBackgroundColor(Color.TRANSPARENT);
        overlay.setVisibility(View.VISIBLE);
        overlay.setAlpha(1f);
        overlay.setOnTouchListener((view, event) -> true);
        overlay.setLayoutParams(new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));

        TextView view = new TextView(this);
        view.setText("Loading Torah Pod...");
        view.setTextColor(Color.rgb(18, 40, 77));
        view.setTextSize(15);
        view.setGravity(Gravity.CENTER);
        view.setTypeface(null, android.graphics.Typeface.BOLD);
        view.setPadding(dp(22), dp(12), dp(22), dp(12));

        GradientDrawable background = new GradientDrawable();
        background.setColor(Color.rgb(255, 250, 240));
        background.setStroke(dp(1), Color.argb(46, 18, 40, 77));
        background.setCornerRadius(dp(24));
        view.setBackground(background);
        view.setElevation(dp(10));

        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.CENTER
        );
        view.setLayoutParams(params);
        overlay.addView(view);
        return overlay;
    }

    private void showStartupIndicator() {
        if (startupOverlay == null) return;
        startupOverlay.animate().cancel();
        startupOverlay.setAlpha(1f);
        startupOverlay.setVisibility(View.VISIBLE);
    }

    private void hideStartupIndicator() {
        if (startupOverlay == null || startupOverlay.getVisibility() != View.VISIBLE) return;
        startupOverlay.animate()
            .alpha(0f)
            .setDuration(180)
            .withEndAction(() -> {
                if (startupOverlay != null) {
                    startupOverlay.setVisibility(View.GONE);
                }
            })
            .start();
    }

    private TextView createRefreshIndicator() {
        TextView view = new TextView(this);
        view.setText("Pull to refresh");
        view.setTextColor(Color.rgb(18, 40, 77));
        view.setTextSize(14);
        view.setGravity(Gravity.CENTER);
        view.setTypeface(null, android.graphics.Typeface.BOLD);
        int horizontal = dp(18);
        int vertical = dp(9);
        view.setPadding(horizontal, vertical, horizontal, vertical);

        GradientDrawable background = new GradientDrawable();
        background.setColor(Color.rgb(255, 250, 240));
        background.setStroke(dp(1), Color.argb(46, 18, 40, 77));
        background.setCornerRadius(dp(22));
        view.setBackground(background);
        view.setElevation(dp(8));
        view.setVisibility(View.INVISIBLE);
        view.setAlpha(0f);
        view.setTranslationY(-dp(56));

        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.TOP | Gravity.CENTER_HORIZONTAL
        );
        params.topMargin = dp(14);
        view.setLayoutParams(params);
        return view;
    }

    private void setupPullToRefresh() {
        webView.setOnTouchListener((view, event) -> {
            if (webView == null) return false;
            switch (event.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    pullStartY = event.getRawY();
                    pullTracking = webView.getScrollY() == 0;
                    pullReady = false;
                    break;
                case MotionEvent.ACTION_MOVE:
                    handlePullMove(event.getRawY());
                    break;
                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    handlePullRelease();
                    break;
                default:
                    break;
            }
            return false;
        });
    }

    private void handlePullMove(float currentY) {
        if (pullRefreshing) return;
        if (!pullTracking) {
            if (webView.getScrollY() != 0) return;
            pullStartY = currentY;
            pullTracking = true;
        }
        if (webView.getScrollY() > 0) {
            hideRefreshIndicator();
            pullReady = false;
            return;
        }

        float drag = currentY - pullStartY;
        if (drag <= dp(8)) {
            hideRefreshIndicator();
            pullReady = false;
            return;
        }

        pullReady = drag >= dp(PULL_REFRESH_THRESHOLD_DP);
        int offset = Math.min(dp(72), Math.round(drag * 0.42f));
        showRefreshIndicator(pullReady ? "Release to refresh" : "Pull to refresh", false);
        refreshIndicator.setTranslationY(-dp(48) + offset);
        refreshIndicator.setAlpha(Math.min(1f, drag / dp(PULL_REFRESH_THRESHOLD_DP)));
    }

    private void handlePullRelease() {
        if (pullTracking && pullReady && !pullRefreshing) {
            triggerPullRefresh();
        } else if (!pullRefreshing) {
            hideRefreshIndicator();
        }
        pullTracking = false;
        pullReady = false;
    }

    private void triggerPullRefresh() {
        pullRefreshing = true;
        showRefreshIndicator("Refreshing...", true);
        if (webView != null) {
            webView.reload();
        }
    }

    private void showRefreshIndicator(String text, boolean pinned) {
        if (refreshIndicator == null) return;
        refreshIndicator.setText(text);
        refreshIndicator.setVisibility(View.VISIBLE);
        refreshIndicator.animate().cancel();
        refreshIndicator.setAlpha(1f);
        if (pinned) {
            refreshIndicator.setTranslationY(dp(12));
        }
    }

    private void hideRefreshIndicator() {
        if (refreshIndicator == null || pullRefreshing) return;
        refreshIndicator.animate()
            .alpha(0f)
            .translationY(-dp(56))
            .setDuration(160)
            .withEndAction(() -> {
                if (refreshIndicator != null && !pullRefreshing) {
                    refreshIndicator.setVisibility(View.INVISIBLE);
                }
            })
            .start();
    }

    private void finishPullRefresh() {
        if (!pullRefreshing) return;
        pullRefreshing = false;
        hideRefreshIndicator();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private void registerNativeAudioReceiver() {
        if (nativeAudioReceiverRegistered) return;
        IntentFilter filter = new IntentFilter(NativeAudioService.ACTION_PROGRESS);
        filter.addAction(NativeAudioService.ACTION_CONTROL);
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

    private void forwardNativeControl(Intent intent) {
        if (webView == null) return;
        try {
            JSONObject payload = new JSONObject();
            payload.put("command", intent.getStringExtra(NativeAudioService.EXTRA_COMMAND));
            String script = "window.TorahPodNativeControl && window.TorahPodNativeControl(" + payload.toString() + ");";
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

    private void startPlaybackService(Intent intent) {
        if (Build.VERSION.SDK_INT >= 26) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
    }

    private boolean isTrustedPage(String value) {
        try {
            Uri uri = Uri.parse(value);
            return "https".equalsIgnoreCase(uri.getScheme()) && "torah-pod.pages.dev".equalsIgnoreCase(uri.getHost())
                && (uri.getPort() == -1 || uri.getPort() == 443);
        } catch (Exception ignored) {
            return false;
        }
    }

    private boolean isHttpsUrl(String value, boolean required) {
        if (value == null || value.length() > 2048) return false;
        if (!required && value.isEmpty()) return true;
        try { return "https".equalsIgnoreCase(Uri.parse(value).getScheme()); }
        catch (Exception ignored) { return false; }
    }

    private boolean validText(JSONObject payload, String key) {
        return payload.optString(key, "").length() <= 300;
    }

    private boolean handleNativePrompt(String raw) {
        try {
            JSONObject envelope = new JSONObject(raw);
            if (envelope.optInt("version", 0) != 1) return false;
            String command = envelope.optString("command", "");
            JSONObject payload = envelope.optJSONObject("payload");
            if (payload == null) payload = new JSONObject();
            Intent intent = new Intent(MainActivity.this, NativeAudioService.class);
            if ("play".equals(command)) {
                if (!isHttpsUrl(payload.optString("src"), true) || !isHttpsUrl(payload.optString("artwork"), false) || !validText(payload, "title") || !validText(payload, "show")) return false;
                intent.setAction(NativeAudioService.ACTION_PLAY);
                intent.putExtra(NativeAudioService.EXTRA_URL, payload.optString("src"));
                intent.putExtra(NativeAudioService.EXTRA_TITLE, payload.optString("title"));
                intent.putExtra(NativeAudioService.EXTRA_SHOW, payload.optString("show"));
                intent.putExtra(NativeAudioService.EXTRA_ARTWORK, payload.optString("artwork"));
                startPlaybackService(intent);
            } else if ("toggle".equals(command) || "stop".equals(command) || "htmlStop".equals(command)) {
                intent.setAction("toggle".equals(command) ? NativeAudioService.ACTION_TOGGLE : "stop".equals(command) ? NativeAudioService.ACTION_STOP : NativeAudioService.ACTION_HTML_STOP);
                startService(intent);
            } else if ("seekBy".equals(command)) {
                int seconds = payload.optInt("seconds", 99999);
                if (seconds < -3600 || seconds > 3600) return false;
                intent.setAction(NativeAudioService.ACTION_SEEK_BY);
                intent.putExtra(NativeAudioService.EXTRA_SECONDS, seconds);
                startService(intent);
            } else if ("seekTo".equals(command)) {
                int position = payload.optInt("seconds", -1);
                if (position < 0 || position > 86400) return false;
                intent.setAction(NativeAudioService.ACTION_SEEK_TO);
                intent.putExtra(NativeAudioService.EXTRA_POSITION, position);
                startService(intent);
            } else if ("htmlPlayback".equals(command)) {
                int position = payload.optInt("position", -1), duration = payload.optInt("duration", -1);
                if (!isHttpsUrl(payload.optString("src"), true) || !validText(payload, "title") || !validText(payload, "show") || position < 0 || duration < 0 || position > 86400 || duration > 86400) return false;
                intent.setAction(NativeAudioService.ACTION_HTML_STATE);
                intent.putExtra(NativeAudioService.EXTRA_URL, payload.optString("src"));
                intent.putExtra(NativeAudioService.EXTRA_TITLE, payload.optString("title"));
                intent.putExtra(NativeAudioService.EXTRA_SHOW, payload.optString("show"));
                intent.putExtra(NativeAudioService.EXTRA_POSITION, position);
                intent.putExtra(NativeAudioService.EXTRA_DURATION, duration);
                intent.putExtra(NativeAudioService.EXTRA_PLAYING, payload.optBoolean("playing", false));
                startPlaybackService(intent);
            } else return false;
            return true;
        } catch (Exception ignored) { return false; }
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
        if (webView == null) {
            super.onBackPressed();
            return;
        }
        webView.evaluateJavascript(
            "(window.TorahPodHandleBack && window.TorahPodHandleBack()) === true",
            value -> {
                if ("true".equals(value)) return;
                if (webView != null && webView.canGoBack()) {
                    webView.goBack();
                    return;
                }
                MainActivity.super.onBackPressed();
            }
        );
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
