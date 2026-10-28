package com.match.bodyexercise;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.util.Log;
import android.view.View;
import android.view.Window;
import android.webkit.ConsoleMessage;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 身体锻炼：一个完全离线的本地记录应用。
 *
 * 页面资源全部来自 assets。数据通过 SharedPreferences 保存。
 * 唯一的网络入口是 AI 报告按钮触发的 post()，不会在启动、渲染或自检时调用。
 */
public class MainActivity extends Activity {
    private static final String TAG = "BodyExercise";
    private static final String PREFS_NAME = "body_exercise_local";
    private static final String DATA_KEY = "data_json";
    private static final String SELFTEST_EXTRA = "selftest";
    private static final String ASSET_PAGE = "file:///android_asset/index.html";

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService networkExecutor = Executors.newCachedThreadPool();
    private SharedPreferences preferences;
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        preferences = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        configureWindow();
        createWebView();
        loadPage(getIntent() != null && getIntent().getBooleanExtra(SELFTEST_EXTRA, false));
    }

    private void configureWindow() {
        Window window = getWindow();
        window.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            window.setStatusBarColor(Color.parseColor("#F2F5F6"));
            window.setNavigationBarColor(Color.WHITE);
        }
        View decor = window.getDecorView();
        int flags = decor.getSystemUiVisibility();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            flags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        }
        decor.setSystemUiVisibility(flags);
    }

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    private void createWebView() {
        webView = new WebView(this);
        webView.setBackgroundColor(Color.parseColor("#F2F5F6"));
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setVerticalScrollBarEnabled(false);
        webView.setHorizontalScrollBarEnabled(false);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadsImagesAutomatically(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setTextZoom(100);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        try {
            settings.setAllowFileAccessFromFileURLs(true);
            settings.setAllowUniversalAccessFromFileURLs(false);
        } catch (Exception ignored) {
            // 这些开关在部分新版 WebView 上已废弃，但本地资源不依赖它们。
        }

        webView.addJavascriptInterface(new NativeBridge(), "Android");
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleNavigation(request.getUrl());
            }

            @Override
            @SuppressWarnings("deprecation")
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleNavigation(Uri.parse(url));
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                Log.d(TAG, "page finished");
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onConsoleMessage(ConsoleMessage message) {
                if (message != null) {
                    Log.d(TAG, "web: " + message.message() + " (" + message.lineNumber() + ")");
                }
                return true;
            }
        });

        if ((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
        }
    }

    private boolean handleNavigation(Uri uri) {
        if (uri == null) return true;
        String url = uri.toString();
        if (url.startsWith(ASSET_PAGE)) return false;
        if (url.startsWith("https://") || url.startsWith("http://")) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (Exception ignored) {
                // 没有浏览器时保持当前页面。
            }
        }
        return true;
    }

    private void loadPage(boolean selfTest) {
        if (webView == null) return;
        String url = ASSET_PAGE + (selfTest ? "?selftest=1" : "");
        webView.loadUrl(url);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (intent != null) {
            loadPage(intent.getBooleanExtra(SELFTEST_EXTRA, false));
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        WebView current = webView;
        if (current == null) {
            super.onBackPressed();
            return;
        }
        current.evaluateJavascript(
                "(function(){try{return window.__androidBack?window.__androidBack():false;}catch(e){return false;}})()",
                value -> {
                    if (!"true".equals(value)) {
                        finish();
                    }
                });
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) webView.onResume();
    }

    @Override
    protected void onPause() {
        if (webView != null) webView.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.removeJavascriptInterface("Android");
            webView.loadUrl("about:blank");
            webView.destroy();
            webView = null;
        }
        networkExecutor.shutdownNow();
        super.onDestroy();
    }

    private final class NativeBridge {
        @JavascriptInterface
        public String loadData() {
            return preferences.getString(DATA_KEY, "");
        }

        @JavascriptInterface
        public void saveData(String json) {
            preferences.edit().putString(DATA_KEY, json == null ? "" : json).apply();
        }

        @JavascriptInterface
        public void toast(String message) {
            if (message == null) return;
            mainHandler.post(() -> Toast.makeText(getApplicationContext(), message, Toast.LENGTH_SHORT).show());
        }

        @JavascriptInterface
        public void vibrate(int milliseconds) {
            int duration = Math.max(1, Math.min(milliseconds, 120));
            try {
                Vibrator vibrator = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
                if (vibrator == null || !vibrator.hasVibrator()) return;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    vibrator.vibrate(VibrationEffect.createOneShot(duration, VibrationEffect.DEFAULT_AMPLITUDE));
                } else {
                    vibrator.vibrate(duration);
                }
            } catch (Exception ignored) {
                // 震动失败不影响记录。
            }
        }

        @JavascriptInterface
        public void post(String url, String headersJson, String body, String requestId, int timeoutSeconds) {
            if (url == null || !(url.startsWith("https://") || url.startsWith("http://"))) {
                sendHttpResult(requestId, 0, "只支持 http/https 地址");
                return;
            }
            final String target = url;
            final String headers = headersJson == null ? "{}" : headersJson;
            final String payload = body == null ? "" : body;
            final int timeout = Math.max(20, Math.min(timeoutSeconds <= 0 ? 120 : timeoutSeconds, 900));
            networkExecutor.execute(() -> performPost(target, headers, payload, requestId, timeout));
        }
    }

    private void performPost(String url, String headersJson, String body, String requestId, int timeoutSeconds) {
        HttpURLConnection connection = null;
        int status = 0;
        String responseText = "";
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(30_000);
            connection.setReadTimeout(timeoutSeconds * 1000);
            connection.setDoOutput(true);
            connection.setUseCaches(false);
            connection.setInstanceFollowRedirects(true);
            connection.setRequestProperty("Accept", "application/json");

            JSONObject headerObject = new JSONObject(headersJson);
            Iterator<String> keys = headerObject.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                if (key == null || key.isEmpty()) continue;
                String lower = key.toLowerCase();
                if ("host".equals(lower) || "content-length".equals(lower)
                        || "connection".equals(lower) || "accept-encoding".equals(lower)) {
                    continue;
                }
                connection.setRequestProperty(key, headerObject.optString(key, ""));
            }

            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(bytes);
                output.flush();
            }

            status = connection.getResponseCode();
            InputStream input = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            responseText = readText(input);
        } catch (Exception error) {
            status = 0;
            responseText = "网络请求失败：" + (error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage());
        } finally {
            if (connection != null) connection.disconnect();
        }
        sendHttpResult(requestId, status, responseText);
        Log.d(TAG, "AI request finished: HTTP " + status);
    }

    private static String readText(InputStream input) throws IOException {
        if (input == null) return "";
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
            char[] buffer = new char[8192];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                builder.append(buffer, 0, count);
                if (builder.length() > 4_000_000) break;
            }
        }
        return builder.toString();
    }

    private void sendHttpResult(String requestId, int status, String text) {
        final String id = requestId == null ? "" : requestId;
        final String response = text == null ? "" : text;
        final String script = "window.__nativeHttp(" + JSONObject.quote(id) + "," + status + ","
                + JSONObject.quote(response) + ");";
        mainHandler.post(() -> {
            WebView current = webView;
            if (current != null) {
                current.evaluateJavascript(script, null);
            }
        });
    }
}
