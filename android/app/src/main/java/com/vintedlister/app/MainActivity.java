package com.vintedlister.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.Toast;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * Prototype: the listing app plus a built-in Vinted window. The seller logs in to Vinted
 * inside this app (the login stays on their phone). "Fill Vinted for me" opens Vinted's
 * sell page here and runs vinted_filler.js, which fills the form; the seller checks it and
 * taps Save draft. Nothing is ever published automatically.
 */
public class MainActivity extends Activity {
    private static final String APP_URL = BuildConfig.APP_URL;
    private static final String VINTED_SELL = "https://www.vinted.co.uk/items/new";
    private static final int FILE_REQUEST = 1, CAMERA_REQUEST = 2;

    private WebView web;
    private Button backToApp;
    private volatile String currentUrl = "";
    private volatile String pendingPayload;
    private String filler;
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest pendingPermission;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        filler = readAsset("vinted_filler.js");
        FrameLayout root = new FrameLayout(this);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));

        backToApp = new Button(this);
        backToApp.setText("← Lister");
        backToApp.setTextColor(Color.parseColor("#F3EDE0"));
        backToApp.setBackgroundColor(Color.parseColor("#2F4A3A"));
        backToApp.setVisibility(View.GONE);
        backToApp.setOnClickListener(v -> web.loadUrl(APP_URL + "drafts"));
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.START);
        lp.setMargins(24, 24, 0, 0);
        root.addView(backToApp, lp);
        setContentView(root);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setUserAgentString(s.getUserAgentString() + " VintedListerApp/0.1");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);
        web.addJavascriptInterface(new Bridge(), "AndroidBridge");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String scheme = request.getUrl().getScheme();
                if ("http".equals(scheme) || "https".equals(scheme)) return false;  // stay inside the app
                try { startActivity(new Intent(Intent.ACTION_VIEW, request.getUrl())); } catch (Exception ignored) { }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                currentUrl = url == null ? "" : url;
                boolean onVinted = isVinted(currentUrl);
                backToApp.setVisibility(onVinted ? View.VISIBLE : View.GONE);
                if (onVinted && pendingPayload != null && currentUrl.contains("/items/new") && filler != null) {
                    // Give Vinted's page a moment to render its form, then fill it.
                    view.postDelayed(() -> view.evaluateJavascript(filler + "\n;window.VintedFiller && window.VintedFiller.run();", null), 2500);
                }
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_REQUEST);
                } catch (Exception e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }

            @Override
            public void onPermissionRequest(PermissionRequest request) {
                // The upload page's live camera. Only our own site gets the camera.
                if (!request.getOrigin().toString().startsWith(APP_URL.replaceAll("/$", ""))) { request.deny(); return; }
                if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(request.getResources());
                } else {
                    pendingPermission = request;
                    requestPermissions(new String[]{Manifest.permission.CAMERA}, CAMERA_REQUEST);
                }
            }
        });

        if (state != null) web.restoreState(state); else web.loadUrl(APP_URL);
    }

    private static boolean isVinted(String url) {
        try {
            String host = Uri.parse(url).getHost();
            return host != null && (host.equals("vinted.co.uk") || host.endsWith(".vinted.co.uk"));
        } catch (Exception e) {
            return false;
        }
    }

    private String readAsset(String name) {
        try (InputStream in = getAssets().open(name); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toString("UTF-8");
        } catch (Exception e) {
            return null;
        }
    }

    /** Called from page JavaScript. Every method checks where it is being called from. */
    private class Bridge {
        @JavascriptInterface
        public boolean isApp() { return true; }

        /** Our site hands over a listing; open Vinted's sell page and fill it there. */
        @JavascriptInterface
        public void startFill(String payloadJson) {
            if (!currentUrl.startsWith(APP_URL)) return;
            pendingPayload = payloadJson;
            runOnUiThread(() -> web.loadUrl(VINTED_SELL));
        }

        /** Vinted's sell page asks for the listing (only there, only once). */
        @JavascriptInterface
        public String getPayload() {
            if (!isVinted(currentUrl)) return null;
            String p = pendingPayload;
            pendingPayload = null;
            return p;
        }

        @JavascriptInterface
        public void openVinted() {
            if (!currentUrl.startsWith(APP_URL)) return;
            runOnUiThread(() -> web.loadUrl("https://www.vinted.co.uk/"));
        }

        /** What the filler found/filled; sent to our server for checking, with the app's sign-in. */
        @JavascriptInterface
        public void report(String reportJson) {
            if (!isVinted(currentUrl)) return;
            new Thread(() -> postReport(reportJson)).start();
        }
    }

    private void postReport(String body) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(APP_URL + "api/vinted-fill-report").openConnection();
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            String cookies = CookieManager.getInstance().getCookie(APP_URL);
            if (cookies != null) c.setRequestProperty("Cookie", cookies);
            try (OutputStream out = c.getOutputStream()) { out.write(body.getBytes(StandardCharsets.UTF_8)); }
            final int code = c.getResponseCode();
            c.disconnect();
            if (body.contains("\"saved\":true")) {
                runOnUiThread(() -> {
                    Toast.makeText(this, code < 400 ? "Saved to your Vinted drafts" : "Saved on Vinted (app not updated)", Toast.LENGTH_LONG).show();
                    web.loadUrl(APP_URL + "drafts");
                });
            }
        } catch (Exception ignored) { }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_REQUEST && fileCallback != null) {
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            fileCallback = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        if (requestCode == CAMERA_REQUEST && pendingPermission != null) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) pendingPermission.grant(pendingPermission.getResources());
            else pendingPermission.deny();
            pendingPermission = null;
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
