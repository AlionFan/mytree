package cn.joybeat.mytree;

import static org.junit.Assert.*;
import android.app.Instrumentation;
import android.content.Intent;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import java.io.File;
import java.lang.reflect.Field;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class AndroidShellTest {
    private Instrumentation instrumentation;
    private MainActivity activity;
    private WebView web;
    @Before public void start() throws Exception {
        instrumentation = InstrumentationRegistry.getInstrumentation();
        Intent intent = new Intent(instrumentation.getTargetContext(),MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        activity = (MainActivity)instrumentation.startActivitySync(intent);
        Field field = MainActivity.class.getDeclaredField("web"); field.setAccessible(true);
        web = (WebView)field.get(activity);
        instrumentation.waitForIdleSync();
    }
    @After public void close() { instrumentation.runOnMainSync(() -> activity.finish()); }
    private String javascript(String script) throws Exception {
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<String> result = new AtomicReference<>();
        instrumentation.runOnMainSync(() -> web.evaluateJavascript(script,value -> { result.set(value); done.countDown(); }));
        assertTrue("JavaScript callback",done.await(10,TimeUnit.SECONDS));
        return result.get();
    }
    private void page() throws Exception {
        instrumentation.runOnMainSync(() -> {
            web.stopLoading();
            android.webkit.WebViewClient original=web.getWebViewClient();
            web.setWebViewClient(new android.webkit.WebViewClient(){
                @Override public android.webkit.WebResourceResponse shouldInterceptRequest(WebView view,android.webkit.WebResourceRequest request){
                    android.webkit.WebResourceResponse blocked=original.shouldInterceptRequest(view,request);
                    if(blocked!=null)return blocked;
                    if(request.getUrl().getPath().equals("/__instrumentation"))return new android.webkit.WebResourceResponse("text/html","UTF-8",new java.io.ByteArrayInputStream("<html><body><h1>Android shell fixture</h1><button id='explorer-sleep' onclick='window.stopped=true'>Stop</button></body></html>".getBytes(java.nio.charset.StandardCharsets.UTF_8)));
                    return original.shouldInterceptRequest(view,request);
                }
                @Override public boolean shouldOverrideUrlLoading(WebView v,android.webkit.WebResourceRequest r){return original.shouldOverrideUrlLoading(v,r);}
                @Override public void onPageStarted(WebView v,String u,android.graphics.Bitmap i){original.onPageStarted(v,u,i);}
                @Override public void onPageFinished(WebView v,String u){original.onPageFinished(v,u);}
                @Override public void onReceivedError(WebView v,android.webkit.WebResourceRequest r,android.webkit.WebResourceError e){original.onReceivedError(v,r,e);}
            });
            web.loadUrl(MainActivity.HOME+"__instrumentation");
        });
        for (int i=0;i<100;i++) {
            if ("true".equals(javascript("!!document.getElementById('explorer-sleep')"))) return;
            Thread.sleep(50);
        }
        fail("fixture load");
    }
    @Test public void exactHttpsOriginOnly() {
        assertTrue(MainActivity.trusted(Uri.parse(MainActivity.HOME)));
        assertTrue(MainActivity.trusted(Uri.parse("https://mytree.joybeat.cn:443/tree?q=1")));
        for (String uri : new String[]{"http://mytree.joybeat.cn/","https://mytree.joybeat.cn.evil.test/","https://evil.test/?next=https://mytree.joybeat.cn/","https://mytree.joybeat.cn:444/","https://user@mytree.joybeat.cn/","file:///data/data/a","content://cn.joybeat.mytree.photos/x","javascript:alert(1)","intent://mytree.joybeat.cn/"})
            assertFalse(uri, MainActivity.trusted(Uri.parse(uri)));
        assertFalse(MainActivity.trusted(null));
    }
    @Test public void hardenedWebSettings() {
        instrumentation.runOnMainSync(() -> {
            WebSettings settings=web.getSettings();
            assertFalse(settings.getAllowFileAccess());
            assertTrue(settings.getJavaScriptEnabled());
            assertTrue(settings.getDomStorageEnabled());
            assertEquals(WebSettings.MIXED_CONTENT_NEVER_ALLOW,settings.getMixedContentMode());
            assertTrue(settings.getMediaPlaybackRequiresUserGesture());
            assertFalse(settings.getJavaScriptCanOpenWindowsAutomatically());
            assertFalse(android.webkit.CookieManager.getInstance().acceptThirdPartyCookies(web));
        });
    }
    @Test public void foreignAndUnknownMediaRequestsDenied() throws Exception {
        page();
        instrumentation.runOnMainSync(() -> {
            FakePermission foreign=new FakePermission("https://evil.test/",PermissionRequest.RESOURCE_VIDEO_CAPTURE);
            web.getWebChromeClient().onPermissionRequest(foreign);
            assertTrue(foreign.denied); assertFalse(foreign.granted);
            FakePermission unknown=new FakePermission(MainActivity.HOME,"future-resource");
            web.getWebChromeClient().onPermissionRequest(unknown);
            assertTrue(unknown.denied); assertFalse(unknown.granted);
        });
    }
    @Test public void foreignFileChooserRejectedAndCallbackCompleted() throws Exception {
        CountDownLatch done=new CountDownLatch(1);
        instrumentation.runOnMainSync(() -> {
            web.stopLoading();
            web.loadDataWithBaseURL("https://evil.test/","<html></html>","text/html","UTF-8",null);
        });
        for (int i=0;i<100;i++) {
            AtomicReference<String> url=new AtomicReference<>();
            instrumentation.runOnMainSync(() -> url.set(web.getUrl()));
            if ("https://evil.test/".equals(url.get())) break;
            Thread.sleep(50);
        }
        instrumentation.runOnMainSync(() -> web.getWebChromeClient().onShowFileChooser(web,value -> {
            assertNull(value); done.countDown();
        },null));
        assertTrue(done.await(5,TimeUnit.SECONDS));
    }
    @Test public void cameraProviderWritesOnlyTemporaryPhotoPaths() throws Exception {
        File dir=new File(activity.getCacheDir(),"captures"); dir.mkdirs();
        File file=new File(dir,"capture-test.jpg"); file.createNewFile();
        Uri valid=Uri.parse("content://cn.joybeat.mytree.photos/capture-test.jpg");
        try (ParcelFileDescriptor fd=activity.getContentResolver().openFileDescriptor(valid,"rw")) { assertNotNull(fd); }
        for (String path : new String[]{"/../shared_prefs/account.xml","/capture-test.jpg/../secret","/other.jpg","/"}) {
            try (ParcelFileDescriptor fd=activity.getContentResolver().openFileDescriptor(Uri.parse("content://cn.joybeat.mytree.photos"+path),"r")) {
                fail("Invalid path accepted: "+path);
            } catch (java.io.FileNotFoundException expected) { }
        }
        file.delete();
    }
    @Test public void backgroundCallsPageMediaStop() throws Exception {
        page();
        instrumentation.runOnMainSync(() -> instrumentation.callActivityOnPause(activity));
        assertEquals("true",javascript("window.stopped===true"));
        instrumentation.runOnMainSync(() -> instrumentation.callActivityOnResume(activity));
    }
    @Test public void runtimePermissionOverlayPreservesPendingGesture() throws Exception {
        page(); FakePermission pending=new FakePermission(MainActivity.HOME,PermissionRequest.RESOURCE_VIDEO_CAPTURE);
        set("mediaRequest",pending);set("waitingMediaPermission",true);
        instrumentation.runOnMainSync(()->instrumentation.callActivityOnPause(activity));
        assertEquals("false",javascript("window.stopped===true"));
        assertTrue((Boolean)get("mediaPermissionPause"));
        instrumentation.runOnMainSync(()->instrumentation.callActivityOnResume(activity));
        assertFalse((Boolean)get("mediaPermissionPause"));
    }
    @Test public void homeDuringRuntimePermissionStopsAndCancelsGesture() throws Exception {
        page(); FakePermission pending=new FakePermission(MainActivity.HOME,PermissionRequest.RESOURCE_VIDEO_CAPTURE);
        set("mediaRequest",pending);set("waitingMediaPermission",true);
        instrumentation.runOnMainSync(()->{instrumentation.callActivityOnPause(activity);instrumentation.callActivityOnStop(activity);});
        assertEquals("true",javascript("window.stopped===true"));assertNull(get("mediaRequest"));assertFalse((Boolean)get("mediaPermissionPause"));
        instrumentation.runOnMainSync(()->{instrumentation.callActivityOnStart(activity);instrumentation.callActivityOnResume(activity);});
        assertNull(get("mediaRequest"));
    }
    @Test public void activityDestroyCompletesPendingFileCallback() throws Exception {
        AtomicReference<Uri[]> value=new AtomicReference<>(new Uri[0]);
        CountDownLatch done=new CountDownLatch(1);
        Field field=MainActivity.class.getDeclaredField("fileCallback"); field.setAccessible(true);
        field.set(activity,(ValueCallback<Uri[]>)uris->{value.set(uris);done.countDown();});
        instrumentation.runOnMainSync(() -> activity.finish());
        assertTrue(done.await(5,TimeUnit.SECONDS)); assertNull(value.get());
    }
    @Test public void documentCancellationCompletesCallback() throws Exception {
        page();
        CountDownLatch done=new CountDownLatch(1);
        AtomicReference<Intent> opened=new AtomicReference<>();
        Instrumentation.ActivityMonitor monitor=new Instrumentation.ActivityMonitor() {
            @Override public Instrumentation.ActivityResult onStartActivity(Intent intent) {
                if (Intent.ACTION_OPEN_DOCUMENT.equals(intent.getAction())) {
                    opened.set(intent); return new Instrumentation.ActivityResult(android.app.Activity.RESULT_CANCELED,null);
                }
                return null;
            }
        };
        instrumentation.addMonitor(monitor);
        try {
            instrumentation.runOnMainSync(() -> web.getWebChromeClient().onShowFileChooser(web,value -> {
                assertNull(value); done.countDown();
            },new Chooser(false)));
            assertTrue(done.await(5,TimeUnit.SECONDS));
            assertNotNull(opened.get());
            assertArrayEquals(new String[]{"image/jpeg","image/png","image/webp","image/gif","image/bmp","application/pdf"},opened.get().getStringArrayExtra(Intent.EXTRA_MIME_TYPES));
        } finally { instrumentation.removeMonitor(monitor); }
    }
    @Test public void cameraCancellationDeletesTemporaryOutput() throws Exception {
        page();
        instrumentation.getUiAutomation().grantRuntimePermission(activity.getPackageName(),android.Manifest.permission.CAMERA);
        CountDownLatch done=new CountDownLatch(1);
        AtomicReference<Uri> output=new AtomicReference<>();
        Instrumentation.ActivityMonitor monitor=new Instrumentation.ActivityMonitor() {
            @Override public Instrumentation.ActivityResult onStartActivity(Intent intent) {
                if (android.provider.MediaStore.ACTION_IMAGE_CAPTURE.equals(intent.getAction())) {
                    output.set(intent.getParcelableExtra(android.provider.MediaStore.EXTRA_OUTPUT));
                    return new Instrumentation.ActivityResult(android.app.Activity.RESULT_CANCELED,null);
                }
                return null;
            }
        };
        instrumentation.addMonitor(monitor);
        try {
            instrumentation.runOnMainSync(() -> web.getWebChromeClient().onShowFileChooser(web,value -> {
                assertNull(value); done.countDown();
            },new Chooser(true)));
            assertTrue(done.await(5,TimeUnit.SECONDS)); assertNotNull(output.get());
            assertFalse(new File(new File(activity.getCacheDir(),"captures"),output.get().getLastPathSegment()).exists());
        } finally { instrumentation.removeMonitor(monitor); }
    }
    private void set(String name,Object value) throws Exception {
        Field field=MainActivity.class.getDeclaredField(name);field.setAccessible(true);field.set(activity,value);
    }
    private Object get(String name) throws Exception {
        Field field=MainActivity.class.getDeclaredField(name);field.setAccessible(true);return field.get(activity);
    }
    private void pendingCamera(ValueCallback<Uri[]> callback) throws Exception {
        set("fileCallback",callback);set("filePage",MainActivity.HOME+"__instrumentation");
        set("fileDocumentGeneration",get("documentGeneration"));
        set("cameraPermissionGeneration",get("fileGeneration"));
    }
    @Test public void permissionAfterHomeCannotLaunchChooser() throws Exception {
        page();CountDownLatch cancelled=new CountDownLatch(1);
        pendingCamera(value->{assertNull(value);cancelled.countDown();});
        java.util.concurrent.atomic.AtomicInteger launches=new java.util.concurrent.atomic.AtomicInteger();
        Instrumentation.ActivityMonitor monitor=new Instrumentation.ActivityMonitor(){
            @Override public Instrumentation.ActivityResult onStartActivity(Intent intent){launches.incrementAndGet();return new Instrumentation.ActivityResult(0,null);}
        };
        instrumentation.addMonitor(monitor);
        try {
            instrumentation.runOnMainSync(()->{
                instrumentation.callActivityOnPause(activity);instrumentation.callActivityOnStop(activity);
                activity.onRequestPermissionsResult(102,new String[]{android.Manifest.permission.CAMERA},new int[]{0});
                instrumentation.callActivityOnStart(activity);instrumentation.callActivityOnResume(activity);
            });
            assertTrue(cancelled.await(5,TimeUnit.SECONDS));assertEquals(0,launches.get());
        } finally{instrumentation.removeMonitor(monitor);}
    }
    @Test public void oldCameraPermissionCannotAffectNewFileRequest() throws Exception {
        page();pendingCamera(value->{});
        long old=(Long)get("fileGeneration");set("fileGeneration",old+1);
        java.util.concurrent.atomic.AtomicInteger callbacks=new java.util.concurrent.atomic.AtomicInteger();
        set("fileCallback",(ValueCallback<Uri[]>)value->callbacks.incrementAndGet());
        instrumentation.runOnMainSync(()->activity.onRequestPermissionsResult(102,new String[]{android.Manifest.permission.CAMERA},new int[]{0}));
        assertEquals(0,callbacks.get());assertNotNull(get("fileCallback"));assertFalse((Boolean)get("pickerInFlight"));
    }
    @Test public void cameraPermissionWaitsForResume() throws Exception {
        page();instrumentation.getUiAutomation().grantRuntimePermission(activity.getPackageName(),android.Manifest.permission.CAMERA);
        CountDownLatch cancelled=new CountDownLatch(1);pendingCamera(value->{assertNull(value);cancelled.countDown();});
        java.util.concurrent.atomic.AtomicInteger launches=new java.util.concurrent.atomic.AtomicInteger();
        Instrumentation.ActivityMonitor monitor=new Instrumentation.ActivityMonitor(){
            @Override public Instrumentation.ActivityResult onStartActivity(Intent intent){launches.incrementAndGet();return new Instrumentation.ActivityResult(0,null);}
        };
        instrumentation.addMonitor(monitor);
        try{
            instrumentation.runOnMainSync(()->{
                instrumentation.callActivityOnPause(activity);
                activity.onRequestPermissionsResult(102,new String[]{android.Manifest.permission.CAMERA},new int[]{0});
            });
            assertEquals(0,launches.get());assertTrue((Boolean)get("deferredCameraLaunch"));
            instrumentation.runOnMainSync(()->instrumentation.callActivityOnResume(activity));
            assertTrue(cancelled.await(5,TimeUnit.SECONDS));assertEquals(1,launches.get());
        }finally{instrumentation.removeMonitor(monitor);}
    }
    @Test public void navigationCancelsCameraRequestBeforeLatePermission() throws Exception {
        page();CountDownLatch cancelled=new CountDownLatch(1);pendingCamera(value->{assertNull(value);cancelled.countDown();});
        instrumentation.runOnMainSync(()->web.loadUrl(MainActivity.HOME+"__instrumentation?new=1"));
        assertTrue(cancelled.await(5,TimeUnit.SECONDS));
        instrumentation.runOnMainSync(()->activity.onRequestPermissionsResult(102,new String[]{android.Manifest.permission.CAMERA},new int[]{0}));
        assertFalse((Boolean)get("pickerInFlight"));assertNull(get("fileCallback"));
    }
    private void focusedWindow() throws Exception {
        // WebView readiness can precede splash exit/input focus when Studio
        // streams a newly booted emulator. Real Back needs an actual window.
        for (int i=0;i<200;i++) {
            java.util.concurrent.atomic.AtomicBoolean ready=new java.util.concurrent.atomic.AtomicBoolean();
            instrumentation.runOnMainSync(() -> ready.set(activity.hasWindowFocus()
                    && activity.getWindow().getDecorView().isShown() && !activity.isFinishing()));
            if (ready.get()) { instrumentation.waitForIdleSync(); return; }
            Thread.sleep(50);
        }
        fail("fixture window did not receive input focus before Back");
    }
    @Test public void nativeBackClosesDialogBeforeLeavingPage() throws Exception {
        page();javascript("var d=document.createElement('dialog');d.innerHTML='<button data-close-test onclick=\"this.parentElement.close()\">Close</button>';document.body.append(d);d.showModal();");
        focusedWindow();
        instrumentation.sendKeyDownUpSync(android.view.KeyEvent.KEYCODE_BACK);
        for(int i=0;i<100;i++){if("false".equals(javascript("d.open")))return;Thread.sleep(30);}
        fail("dialog remained open");
    }
    @Test public void navigationDismissesNativeExternalConfirmation() throws Exception {
        page();
        instrumentation.runOnMainSync(()->web.getWebViewClient().shouldOverrideUrlLoading(web,new android.webkit.WebResourceRequest(){
            @Override public Uri getUrl(){return Uri.parse("https://example.com/");}
            @Override public boolean isForMainFrame(){return true;}
            @Override public boolean isRedirect(){return false;}
            @Override public boolean hasGesture(){return true;}
            @Override public String getMethod(){return "GET";}
            @Override public java.util.Map<String,String> getRequestHeaders(){return java.util.Collections.emptyMap();}
        }));
        assertNotNull(get("externalDialog"));
        instrumentation.runOnMainSync(()->web.loadUrl(MainActivity.HOME+"__instrumentation?new=1"));
        for(int i=0;i<100;i++){
            java.util.concurrent.atomic.AtomicBoolean gone=new java.util.concurrent.atomic.AtomicBoolean();
            instrumentation.runOnMainSync(()->{try{gone.set(get("externalDialog")==null);}catch(Exception e){throw new RuntimeException(e);}});
            if(gone.get())return;Thread.sleep(30);
        }
        fail("native external confirmation survived navigation");
    }
    private static final class Chooser extends WebChromeClient.FileChooserParams {
        private final boolean capture;
        Chooser(boolean capture) { this.capture=capture; }
        @Override public int getMode(){return MODE_OPEN;}
        @Override public String[] getAcceptTypes(){return new String[]{"image/*"};}
        @Override public boolean isCaptureEnabled(){return capture;}
        @Override public CharSequence getTitle(){return "File";}
        @Override public String getFilenameHint(){return null;}
        @Override public Intent createIntent(){return new Intent(Intent.ACTION_OPEN_DOCUMENT);}
    }
    private static final class FakePermission extends PermissionRequest {
        final Uri origin; final String resource; boolean denied,granted;
        FakePermission(String uri,String resource){origin=Uri.parse(uri);this.resource=resource;}
        @Override public Uri getOrigin(){return origin;}
        @Override public String[] getResources(){return new String[]{resource};}
        @Override public void grant(String[] resources){granted=true;}
        @Override public void deny(){denied=true;}
    }
}
