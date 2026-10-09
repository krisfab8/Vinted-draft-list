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
    private volatile String pendingLogin;   // "vinted"/"ebay": tap that site's own Log in / Sign in once the page loads
    private String loginSite = "vinted";
    private volatile String bridgeKey;       // given to our Vinted filler only; required by getPayload/report
    private long loginUntil;                // keep trying to reach Vinted's login until this time (ms)
    private int loginRun;                   // each new page restarts the attempts; older runs stop
    private boolean loginClicked;
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
                backToApp.setVisibility(isMarketplace(currentUrl) ? View.VISIBLE : View.GONE);
                boolean onMarket = isMarketplace(currentUrl);
                if (onMarket && pendingLogin != null) {
                    loginSite = pendingLogin;
                    pendingLogin = null;
                    loginUntil = System.currentTimeMillis() + 45000;
                    loginClicked = false;
                    loginNavDone = false;
                    loginSteps.setLength(0);
                    lastLoginStep = "";
                    Toast.makeText(MainActivity.this, "Finding " + siteName() + "'s " + loginWord() + "\u2026", Toast.LENGTH_SHORT).show();
                }
                if (onMarket && System.currentTimeMillis() < loginUntil) {
                    // Login addresses change (and eBay's errors when opened cold); the sites' own buttons don't.
                    // Pages draw late, so keep looking (header, menu, pop-ups) until the login options show.
                    int run = ++loginRun;
                    view.postDelayed(() -> loginStep(view, run, 0), 1000);
                }
                if (onVinted && pendingPayload != null && currentUrl.contains("/items/new") && filler != null) {
                    // Give Vinted's page a moment to render its form, then fill it.
                    // A fresh one-time key, handed only to our filler (inside its own function, not on window),
                    // so adverts or other frames on Vinted's page can't use the bridge.
                    bridgeKey = java.util.UUID.randomUUID().toString();
                    final String run = "(function(__vlKey){" + filler + "\n;window.VintedFiller && window.VintedFiller.run();})('" + bridgeKey + "');";
                    view.postDelayed(() -> view.evaluateJavascript(run, null), 2500);
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
                Uri origin = request.getOrigin(), ours = Uri.parse(APP_URL);
                if (!"https".equals(origin.getScheme()) || origin.getHost() == null || !origin.getHost().equals(ours.getHost())) {
                    request.deny(); return;   // exact host: a lookalike like ours.evil.tld never gets the camera
                }
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

    /** One look at Vinted's page: "form" = login options showing, "tapped"/"opened" = clicked a Log in,
     *  "in" = already logged in, "menu" = opened the \u2630 menu (on phones Vinted keeps Sign up | Log in there,
     *  and it only exists once opened), "nav" = followed a login link, "cookies" = chose essential cookies,
     *  "country"/"country-ok" = picked United Kingdom, otherwise "none|what it saw". */
    private static final String LOGIN_STEP =
        "(function(allowNav,site){var vinted=site!=='ebay';var all=Array.prototype.slice.call(document.querySelectorAll('a,button,[role=button]'));"
        + "var shown=function(e){var r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.right>0&&r.left<innerWidth"
        + "&&getComputedStyle(e).visibility!=='hidden';};"
        + "var els=all.filter(function(e){return shown(e)&&!e.dataset.vlTapped"
        + "&&!(e.closest('form')&&(e.type==='submit'||e.closest('form').querySelector('input[type=password]')));});"
        + "var txt=function(e){return (e.innerText||e.textContent||'').trim();};"
        // Cookie pop-up: essential only (never accept advertising cookies for the seller); then the menu may be retried.
        + "var ck=els.find(function(e){return /^(choose essential|essential only|reject all|decline all|decline|accept essential( cookies)?|use necessary cookies only)$/i.test(txt(e));});"
        + "if(ck){ck.dataset.vlTapped='1';ck.click();delete document.documentElement.dataset.vlMenu;return 'cookies';}"
        // Country picker: United Kingdom, then its Continue/Confirm.
        + "var de=document.documentElement,body=(document.body&&document.body.innerText)||'';"
        + "if(vinted&&/countr/i.test(body)){var uk=Array.prototype.slice.call(document.querySelectorAll('a,button,[role=button],[role=option],[role=radio],li,label,span,div'))"
        + ".filter(function(e){return shown(e)&&!e.dataset.vlTapped&&/^united kingdom$/i.test(txt(e));}).pop();"
        + "if(uk&&!de.dataset.vlCountry){uk.dataset.vlTapped='1';uk.click();de.dataset.vlCountry=1;return 'country';}"
        + "if(de.dataset.vlCountry){var go=els.find(function(e){return /^(continue|confirm|save|done|next)$/i.test(txt(e));});"
        + "if(go){delete de.dataset.vlCountry;go.dataset.vlTapped='1';go.click();return 'country-ok';}}}"
        + "var exact=els.find(function(e){return /^(log ?in|sign ?in)$/i.test(txt(e));});"
        + "if(exact){exact.dataset.vlTapped='1';exact.click();return 'tapped';}"
        + "if(document.querySelector('input[type=password],input[name=username],input[name=userid],input[type=email]')"
        + "||els.some(function(e){return /log in with email|continue with (google|apple|facebook)/i.test(txt(e));}))return 'form';"
        + "var any=els.find(function(e){return /log ?in|sign ?in/i.test(txt(e));});"
        + "if(any){any.dataset.vlTapped='1';any.click();return 'opened';}"
        + "if(vinted&&document.querySelector('a[href*=inbox],[data-testid*=user-menu],[data-testid*=header-user]'))return 'in';"
        + "if(vinted&&!document.documentElement.dataset.vlMenu){var hdr=document.querySelector('header')||document.body;"
        + "var lbl=function(e){return (e.getAttribute('aria-label')||'')+' '+(e.getAttribute('data-testid')||'')+' '+(e.className||'');};"
        + "var menu=els.find(function(e){return /menu|burger|navigation|hamburger/i.test(lbl(e));})"
        + "||Array.prototype.slice.call(hdr.querySelectorAll('button,[role=button],a')).filter(function(e){"
        + "return shown(e)&&!txt(e)&&e.querySelector('svg,span,i,img');}).pop();"
        + "if(menu){document.documentElement.dataset.vlMenu=1;menu.click();return 'menu';}}"
        + "var here=location.href.split('#')[0];"
        + "var link=all.find(function(e){var h=e.href||'';return /^https?:/.test(h)&&h.split('#')[0]!==here"
        + "&&/select_type|\\/login|\\/signin|\\/auth/i.test(h);});"
        + "if(allowNav&&link){location.href=link.href;return 'nav';}"
        + "return 'none|'+els.map(txt).filter(function(t){return t&&t.length<24;}).slice(0,8).join(', ');})";

    private boolean loginNavDone;
    private final StringBuilder loginSteps = new StringBuilder();
    private String lastLoginStep = "";

    private String siteName() { return "ebay".equals(loginSite) ? "eBay" : "Vinted"; }
    private String loginWord() { return "ebay".equals(loginSite) ? "Sign in" : "Log in"; }

    private void loginStep(WebView view, int run, int attempt) {
        if (run != loginRun || System.currentTimeMillis() > loginUntil || !isMarketplace(currentUrl)) return;
        view.evaluateJavascript(LOGIN_STEP + "(" + !loginNavDone + ",'" + loginSite + "')", result -> {
            if (run != loginRun) return;
            String r = result == null ? "" : result.replaceAll("^\"|\"$", "").replace("\\\"", "\"");
            if (r.equals("tapped") || r.equals("opened") || r.equals("menu")) loginClicked = true;
            // "menu": opened Vinted's \u2630 menu; the next look finds its Log in.
            if (r.equals("nav")) loginNavDone = true;   // a new page restarts the search; keep looking meanwhile
            String step = r.split("\\|")[0];
            if (!step.equals(lastLoginStep) && loginSteps.length() < 120)
                loginSteps.append(loginSteps.length() == 0 ? "" : " \u203a ").append(step.isEmpty() ? "?" : step);
            lastLoginStep = step;
            if (r.equals("form")) { loginUntil = 0; return; }   // login options are showing: done
            if (r.equals("in")) {
                loginUntil = 0;
                Toast.makeText(this, "You're already logged in to " + siteName() + " \u2713", Toast.LENGTH_LONG).show();
                return;
            }
            if (attempt < 30) { view.postDelayed(() -> loginStep(view, run, attempt + 1), 800); return; }
            loginUntil = 0;
            String saw = r.startsWith("none|") ? r.substring(5) : "";
            Toast.makeText(this, "Couldn't reach " + siteName() + "'s " + loginWord() + ": tap it yourself. (Tried: " + loginSteps
                + (saw.isEmpty() ? "" : "; saw: " + saw) + ")", Toast.LENGTH_LONG).show();
        });
    }

    /** Vinted, eBay or Depop: shows the "← Lister" button so you can always get back. */
    private static boolean isMarketplace(String url) {
        try {
            String host = Uri.parse(url).getHost();
            if (host == null) return false;
            return host.equals("vinted.co.uk") || host.endsWith(".vinted.co.uk") || host.equals("ebay.co.uk")
                || host.endsWith(".ebay.co.uk") || host.equals("depop.com") || host.endsWith(".depop.com");
        } catch (Exception e) {
            return false;
        }
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

        /** Shown in Settings so you can check which build is installed. */
        @JavascriptInterface
        public String appVersion() { return BuildConfig.VERSION_NAME; }

        /** Our site hands over a listing; open Vinted's sell page and fill it there. */
        @JavascriptInterface
        public void startFill(String payloadJson) {
            if (!currentUrl.startsWith(APP_URL)) return;
            pendingPayload = payloadJson;
            runOnUiThread(() -> web.loadUrl(VINTED_SELL));
        }

        /** Vinted's sell page asks for the listing (only there, only once). */
        @JavascriptInterface
        public String getPayload(String key) {
            if (!isVinted(currentUrl) || !keyOk(key)) return null;
            String p = pendingPayload;
            pendingPayload = null;
            return p;
        }

        private boolean keyOk(String key) {
            String expected = bridgeKey;
            return expected != null && key != null && java.security.MessageDigest.isEqual(expected.getBytes(), key.getBytes());
        }

        @JavascriptInterface
        public void openVinted() { openSite("vinted"); }

        /** Log in buttons in our Settings: go straight to that marketplace's login (only from our site). */
        @JavascriptInterface
        public void openSite(String platform) {
            if (!currentUrl.startsWith(APP_URL)) return;
            final String url;
            if ("ebay".equals(platform)) { url = "https://www.ebay.co.uk/"; pendingLogin = "ebay"; }
            else if ("depop".equals(platform)) url = "https://www.depop.com/login/";
            else { url = "https://www.vinted.co.uk/"; pendingLogin = "vinted"; }
            runOnUiThread(() -> web.loadUrl(url));
        }

        /** What the filler found/filled; sent to our server for checking, with the app's sign-in. */
        @JavascriptInterface
        public void report(String key, String reportJson) {
            if (!isVinted(currentUrl) || !keyOk(key)) return;
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
