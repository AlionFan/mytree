package cn.joybeat.mytree;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.os.Message;
import android.provider.MediaStore;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.HttpAuthHandler;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import java.io.File;
import java.io.ByteArrayInputStream;
import java.util.ArrayList;
import java.util.UUID;

public final class MainActivity extends Activity {
    static final String HOME = "https://mytree.joybeat.cn/";
    private static final int FILE = 101, CAMERA_PERMISSION = 102, WEB_PERMISSION = 103;
    private WebView web;
    private ProgressBar progress;
    private LinearLayout errorPanel;
    private AlertDialog externalDialog;
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest mediaRequest;
    private Uri cameraUri;
    private String retryUrl = HOME;
    private boolean foreground, waitingMediaPermission, handlingBack, mediaPermissionPause;
    private long lifecycleGeneration;
    private long documentGeneration, fileGeneration, fileDocumentGeneration;
    private long cameraPermissionGeneration = -1;
    private String filePage;
    private boolean pickerInFlight, deferredCameraLaunch;
    private long backPressedAt;

    static boolean trusted(Uri uri) {
        return uri != null && "https".equalsIgnoreCase(uri.getScheme())
                && "mytree.joybeat.cn".equalsIgnoreCase(uri.getHost())
                && (uri.getPort() == -1 || uri.getPort() == 443) && uri.getUserInfo() == null;
    }
    private int dp(int value) { return (int)(value * getResources().getDisplayMetrics().density + .5f); }
    private void toast(String text) { Toast.makeText(this, text, Toast.LENGTH_LONG).show(); }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(247,247,245));
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        web = new WebView(this);
        web.setId(View.generateViewId());
        root.addView(web, new FrameLayout.LayoutParams(-1,-1));
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setContentDescription("正在载入小树同学");
        root.addView(progress, new FrameLayout.LayoutParams(-1,dp(3),Gravity.TOP));
        errorPanel = new LinearLayout(this);
        errorPanel.setOrientation(LinearLayout.VERTICAL);
        errorPanel.setGravity(Gravity.CENTER);
        errorPanel.setPadding(dp(28),dp(28),dp(28),dp(28));
        errorPanel.setBackgroundColor(Color.rgb(247,247,245));
        TextView error = new TextView(this);
        error.setText("暂时无法连接小树同学\n请检查网络后重试。已保存的学习记录仍在账号中。");
        error.setTextColor(Color.rgb(31,54,49));
        error.setTextSize(18);
        error.setGravity(Gravity.CENTER);
        errorPanel.addView(error);
        Button retry = new Button(this); retry.setText("重新连接");
        retry.setOnClickListener(v -> web.loadUrl(trusted(Uri.parse(retryUrl)) ? retryUrl : HOME));
        errorPanel.addView(retry, new LinearLayout.LayoutParams(-1,dp(52)));
        Button home = new Button(this); home.setText("回到首页");
        home.setOnClickListener(v -> web.loadUrl(HOME));
        errorPanel.addView(home, new LinearLayout.LayoutParams(-1,dp(52)));
        root.addView(errorPanel, new FrameLayout.LayoutParams(-1,-1));
        errorPanel.setVisibility(View.GONE);
        setContentView(root);
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::onBackPressed);
        }

        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true); // only chooser-returned content URIs; never navigated
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setGeolocationEnabled(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(true);
        settings.setUserAgentString(settings.getUserAgentString() + " MyTreeAndroid/0.2");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        web.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                // Includes POST and redirects, which shouldOverrideUrlLoading does not cover.
                // All network resources must use the exact service origin. Blob/data are
                // renderer-local previews, not network or native filesystem access.
                String scheme = r.getUrl().getScheme();
                // The current web application submits through same-origin fetch APIs,
                // never top-level form POST. Reject it rather than rely on navigation
                // callbacks (which omit POST) or on redirect behavior for a POST body.
                boolean safeMainMethod = !r.isForMainFrame() || "GET".equals(r.getMethod()) || "HEAD".equals(r.getMethod());
                if (safeMainMethod && trusted(r.getUrl())) return null;
                if (!r.isForMainFrame() && ("blob".equals(scheme) || "data".equals(scheme))) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked",
                        java.util.Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
            }
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                if (trusted(r.getUrl())) return false;
                if (r.isForMainFrame() && r.hasGesture()) external(r.getUrl());
                return true;
            }
            @Override public void onPageStarted(WebView v, String url, Bitmap icon) {
                dismissExternalDialog();
                documentGeneration++;
                finishFile(null); deleteCancelledPhoto();
                cancelMediaRequest();
                if (!trusted(Uri.parse(url))) { v.stopLoading(); showError(); return; }
                errorPanel.setVisibility(View.GONE);
                progress.setVisibility(View.VISIBLE);
                if (trusted(Uri.parse(url))) retryUrl = url;
            }
            @Override public void onPageFinished(WebView v, String url) {
                if (!trusted(Uri.parse(url))) { v.stopLoading(); showError(); return; }
                progress.setVisibility(View.GONE);
                CookieManager.getInstance().flush();
            }
            @Override public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame()) showError();
            }
            @Override public void onReceivedHttpError(WebView v, WebResourceRequest r, WebResourceResponse response) {
                if (r.isForMainFrame() && response.getStatusCode() >= 400) showError();
            }
            @Override public void onReceivedSslError(WebView v, SslErrorHandler handler, SslError error) {
                handler.cancel(); showError();
            }
            @Override public void onReceivedHttpAuthRequest(WebView v, HttpAuthHandler handler, String host, String realm) {
                handler.cancel();
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) { progress.setProgress(value); }
            @Override public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (pickerInFlight) { callback.onReceiveValue(null); return true; }
                finishFile(null);
                deleteCancelledPhoto();
                if (!trusted(Uri.parse(v.getUrl())) || !foreground) { callback.onReceiveValue(null); return true; }
                if (cameraPermissionGeneration != -1) {
                    callback.onReceiveValue(null); toast("请先完成权限选择，再重新拍照。"); return true;
                }
                fileCallback = callback;
                filePage = v.getUrl(); fileDocumentGeneration = documentGeneration;
                if (params.isCaptureEnabled()) {
                    if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                        cameraPermissionGeneration = fileGeneration;
                        requestPermissions(new String[]{Manifest.permission.CAMERA}, CAMERA_PERMISSION);
                    } else camera();
                } else documents();
                return true;
            }
            @Override public void onPermissionRequest(PermissionRequest request) {
                cancelMediaRequest();
                if (!foreground || !trusted(request.getOrigin()) || !trusted(Uri.parse(web.getUrl()))) { request.deny(); return; }
                ArrayList<String> permissions = new ArrayList<>();
                for (String resource : request.getResources()) {
                    String permission;
                    if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)) permission = Manifest.permission.CAMERA;
                    else if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)) permission = Manifest.permission.RECORD_AUDIO;
                    else { request.deny(); return; }
                    if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) permissions.add(permission);
                }
                mediaRequest = request;
                if (permissions.isEmpty()) grantMedia();
                else {
                    waitingMediaPermission = true;
                    requestPermissions(permissions.toArray(new String[0]), WEB_PERMISSION);
                }
            }
            @Override public void onPermissionRequestCanceled(PermissionRequest request) {
                if (mediaRequest == request) mediaRequest = null;
            }
            @Override public boolean onCreateWindow(WebView v, boolean dialog, boolean gesture, Message message) {
                // Handle a user-clicked target=_blank link without creating an unrestricted WebView.
                if (!gesture) return false;
                String link = v.getHitTestResult().getExtra();
                if (link != null) {
                    Uri uri = Uri.parse(link);
                    if (trusted(uri)) web.loadUrl(link); else external(uri);
                }
                return false;
            }
        });
        web.setDownloadListener((url, agent, disposition, mime, length) ->
                toast("请在浏览器中打开网页下载文件。"));
        if (state == null || web.restoreState(state) == null) web.loadUrl(HOME);
        else if (!trusted(Uri.parse(web.getUrl()))) web.loadUrl(HOME);
        if (state != null && state.getBoolean("file_pending")) toast("文件选择已中断，请重新选择。 ");
        // Delete only stale camera files; never delete the current upload on a short app switch.
        File[] files = new File(getCacheDir(), "captures").listFiles();
        if (files != null) for (File file : files)
            if (System.currentTimeMillis() - file.lastModified() > 86400000L) file.delete();
    }
    private void showError() { progress.setVisibility(View.GONE); errorPanel.setVisibility(View.VISIBLE); }
    private void external(Uri uri) {
        if (!"https".equalsIgnoreCase(uri.getScheme()) && !"http".equalsIgnoreCase(uri.getScheme())) {
            toast("此链接无法在小树同学中打开。"); return;
        }
        dismissExternalDialog();
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("在浏览器中打开？")
                .setMessage(uri.getHost()).setNegativeButton("取消",null)
                .setPositiveButton("打开",(d,w) -> {
                    try { startActivity(new Intent(Intent.ACTION_VIEW,uri).addCategory(Intent.CATEGORY_BROWSABLE)); }
                    catch (Exception e) { toast("未找到可用浏览器。"); }
                }).create();
        externalDialog = dialog;
        dialog.setOnDismissListener(d -> { if (externalDialog == dialog) externalDialog = null; });
        dialog.show();
    }
    private void dismissExternalDialog() {
        if (externalDialog != null) { externalDialog.dismiss(); externalDialog = null; }
    }
    private void documents() {
        if (!validFileRequest() || !foreground) return;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/jpeg","image/png","image/webp","image/gif","image/bmp","application/pdf"});
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try { pickerInFlight = true; startActivityForResult(intent,FILE); }
        catch (Exception e) { pickerInFlight = false; finishFile(null); toast("无法打开文件选择器，请检查系统文件应用。"); }
    }
    private void camera() {
        if (!validFileRequest() || !foreground) return;
        try {
            File directory = new File(getCacheDir(),"captures");
            if (!directory.exists() && !directory.mkdirs()) throw new IllegalStateException();
            File photo = new File(directory,"capture-" + UUID.randomUUID() + ".jpg");
            if (!photo.createNewFile()) throw new IllegalStateException();
            cameraUri = Uri.parse("content://" + getPackageName() + ".photos/" + photo.getName());
            Intent intent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
            intent.putExtra(MediaStore.EXTRA_OUTPUT,cameraUri);
            intent.setClipData(ClipData.newRawUri("photo",cameraUri));
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            pickerInFlight = true;
            startActivityForResult(intent,FILE);
        } catch (Exception e) {
            pickerInFlight = false;
            deleteCancelledPhoto();
            toast("无法打开相机，可以改选图片或 PDF。"); documents();
        }
    }
    private void deleteCancelledPhoto() {
        if (cameraUri != null) {
            revokeUriPermission(cameraUri,Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            new File(new File(getCacheDir(),"captures"),cameraUri.getLastPathSegment()).delete();
            cameraUri = null;
        }
    }
    private void finishFile(Uri[] uris) {
        ValueCallback<Uri[]> callback = fileCallback; fileCallback = null;
        fileGeneration++; deferredCameraLaunch = false;
        if (callback != null) callback.onReceiveValue(uris);
    }
    private boolean validFileRequest() {
        return fileCallback != null && fileDocumentGeneration == documentGeneration
                && filePage != null && filePage.equals(web.getUrl()) && trusted(Uri.parse(filePage));
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request,result,data);
        if (request != FILE) return;
        pickerInFlight = false;
        if (result != RESULT_OK || !validFileRequest()) { deleteCancelledPhoto(); finishFile(null); return; }
        if (cameraUri != null) {
            revokeUriPermission(cameraUri,Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            finishFile(new Uri[]{cameraUri}); cameraUri = null; return;
        }
        Uri uri = data == null ? null : data.getData();
        // Never return file:, an app-private provider URI, or an arbitrary activity result.
        if (uri != null && "content".equals(uri.getScheme()) && !(getPackageName()+".photos").equals(uri.getAuthority())) {
            try (android.content.res.AssetFileDescriptor ignored = getContentResolver().openAssetFileDescriptor(uri,"r")) {
                if (ignored == null) throw new IllegalStateException();
                finishFile(new Uri[]{uri}); return;
            } catch (Exception e) { toast("无法读取文件，请重新选择。"); }
        }
        finishFile(null);
    }
    private void cancelMediaRequest() {
        waitingMediaPermission = false;
        if (mediaRequest != null) { mediaRequest.deny(); mediaRequest = null; }
    }
    private void grantMedia() {
        PermissionRequest request = mediaRequest; mediaRequest = null;
        if (request == null) return;
        if (!foreground || !trusted(request.getOrigin()) || !trusted(Uri.parse(web.getUrl()))) { request.deny(); return; }
        for (String resource : request.getResources()) {
            String p = PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource) ? Manifest.permission.CAMERA : Manifest.permission.RECORD_AUDIO;
            if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) { request.deny(); return; }
        }
        request.grant(request.getResources());
    }
    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code,permissions,results);
        if (code == CAMERA_PERMISSION) {
            long generation = cameraPermissionGeneration; cameraPermissionGeneration = -1;
            if (generation != fileGeneration || !validFileRequest()) return;
            deferredCameraLaunch = true;
            if (foreground) resumeCameraChoice();
        } else if (code == WEB_PERMISSION) {
            waitingMediaPermission = false;
            if (foreground) grantMedia(); // otherwise wait until onResume, never grant in background
        }
    }
    @Override protected void onSaveInstanceState(Bundle state) {
        web.saveState(state); state.putBoolean("file_pending",fileCallback != null);
        super.onSaveInstanceState(state);
    }
    @Override protected void onResume() {
        super.onResume(); foreground = true; lifecycleGeneration++; mediaPermissionPause = false;
        if (web != null) web.onResume();
        if (!waitingMediaPermission) grantMedia();
        resumeCameraChoice();
    }
    private void resumeCameraChoice() {
        if (!foreground || !deferredCameraLaunch) return;
        deferredCameraLaunch = false;
        if (!validFileRequest()) { finishFile(null); return; }
        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) camera();
        else { toast("相机权限未开启，可以上传图片或 PDF。"); documents(); }
    }
    @Override protected void onPause() {
        foreground = false;
        long pauseGeneration = ++lifecycleGeneration;
        CookieManager.getInstance().flush();
        // The system runtime permission overlay is still part of this foreground
        // gesture. Preserve it; a real background transition always reaches onStop.
        if (waitingMediaPermission && mediaRequest != null) mediaPermissionPause = true;
        else stopPageMedia(pauseGeneration);
        super.onPause();
    }
    private void stopPageMedia(long pauseGeneration) {
        // Use the page's existing stop action, closing its tracks/recorder/AudioContext and requests.
        // Keep capture/speech cancellation ordered before pausing rendering.
        // The generation guard also prevents a late pause after resume.
        web.evaluateJavascript("document.getElementById('explorer-sleep')?.click();document.querySelectorAll('audio,video').forEach(e=>{e.pause();if(e.srcObject)e.srcObject.getTracks().forEach(t=>t.stop());});", ignored -> {
            if (!foreground && lifecycleGeneration == pauseGeneration && !isDestroyed()) {
                if (BuildConfig.DEBUG) android.util.Log.d("MyTreeMedia", "page stopped before WebView pause");
                web.onPause();
            }
        });
    }
    @Override protected void onStop() {
        foreground = false; cancelMediaRequest();
        if (mediaPermissionPause) { mediaPermissionPause = false; stopPageMedia(lifecycleGeneration); }
        // Keep an already-open native picker alive. A permission result alone must
        // never bring an inactive app's chooser to the foreground after Home.
        if (!pickerInFlight) { finishFile(null); deleteCancelledPhoto(); }
        super.onStop();
    }
    @Override protected void onDestroy() {
        dismissExternalDialog();
        finishFile(null); cancelMediaRequest();
        deleteCancelledPhoto();
        if (web != null) { web.stopLoading(); web.destroy(); }
        super.onDestroy();
    }
    @Override public void onBackPressed() {
        if (BuildConfig.DEBUG) android.util.Log.d("MyTreeBack", "dispatch busy=" + handlingBack
                + " errorPanel=" + (errorPanel.getVisibility() == View.VISIBLE));
        if (handlingBack) return;
        if (errorPanel.getVisibility() != View.VISIBLE && trusted(Uri.parse(web.getUrl()))) {
            handlingBack = true;
            web.evaluateJavascript("(()=>{if(window.mathVirtualKeyboard?.visible){window.mathVirtualKeyboard.hide();return true;}const ds=document.querySelectorAll('dialog[open]'),d=ds[ds.length-1];if(!d)return false;const b=Array.from(d.querySelectorAll('button')).find(b=>!b.disabled&&(Array.from(b.attributes).some(a=>a.name.startsWith('data-close-'))||b.textContent.trim()==='关闭'));if(b)b.click();else if(d.dispatchEvent(new Event('cancel',{cancelable:true})))d.close();return true;})()", result -> {
                if (BuildConfig.DEBUG) android.util.Log.d("MyTreeBack", "page consumed=" + result);
                handlingBack = false;
                if (!"true".equals(result) && !isFinishing()) navigateBack();
            });
        } else navigateBack();
    }
    private void navigateBack() {
        if (errorPanel.getVisibility() == View.VISIBLE && web.canGoBack()) {
            errorPanel.setVisibility(View.GONE); web.goBack();
        } else if (web.canGoBack()) web.goBack();
        else if (System.currentTimeMillis() - backPressedAt < 2000) finish();
        else { backPressedAt = System.currentTimeMillis(); toast("再按一次返回退出小树同学。"); }
    }
}
