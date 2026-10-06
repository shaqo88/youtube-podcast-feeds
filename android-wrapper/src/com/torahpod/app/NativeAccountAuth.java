package com.torahpod.app;

import android.app.Activity;
import android.os.CancellationSignal;
import androidx.credentials.Credential;
import androidx.credentials.CredentialManager;
import androidx.credentials.CredentialManagerCallback;
import androidx.credentials.ClearCredentialStateRequest;
import androidx.credentials.CustomCredential;
import androidx.credentials.GetCredentialRequest;
import androidx.credentials.GetCredentialResponse;
import androidx.credentials.exceptions.ClearCredentialException;
import androidx.credentials.exceptions.GetCredentialException;
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption;
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;
import com.google.firebase.auth.GoogleAuthProvider;
import org.json.JSONObject;

/** Native identity only. OAuth never runs inside the WebView. */
final class NativeAccountAuth {
    interface Result { void finish(JSONObject value); }
    private final Activity activity;
    private final CredentialManager credentials;
    private FirebaseAuth auth;
    private CancellationSignal cancellation;
    private FirebaseAuth.AuthStateListener listener;
    private boolean signingIn;

    NativeAccountAuth(Activity activity, Result changed) {
        this.activity = activity;
        credentials = CredentialManager.create(activity);
        if (BuildConfig.FIREBASE_APPLICATION_ID.isEmpty() || BuildConfig.GOOGLE_WEB_CLIENT_ID.isEmpty()) return;
        FirebaseApp app;
        try { app = FirebaseApp.getInstance(); }
        catch (IllegalStateException ignored) {
            app = FirebaseApp.initializeApp(activity, new FirebaseOptions.Builder()
                .setApplicationId(BuildConfig.FIREBASE_APPLICATION_ID)
                .setApiKey(BuildConfig.FIREBASE_API_KEY).setProjectId(BuildConfig.FIREBASE_PROJECT_ID).build());
        }
        auth = FirebaseAuth.getInstance(app);
        listener = firebase -> changed.finish(state("authState"));
        auth.addAuthStateListener(listener);
    }

    boolean available() { return auth != null; }
    JSONObject state(String event) {
        JSONObject value = new JSONObject();
        try {
            value.put("event", event);
            FirebaseUser user = auth == null ? null : auth.getCurrentUser();
            if (user == null) value.put("user", JSONObject.NULL);
            else value.put("user", new JSONObject().put("uid", user.getUid()).put("displayName", user.getDisplayName()));
        } catch (Exception ignored) { }
        return value;
    }
    private void error(Result result, String code) {
        JSONObject value = new JSONObject(); try { value.put("error", code); } catch (Exception ignored) { }
        result.finish(value);
    }
    void command(String command, JSONObject payload, Result result) {
        if (!available()) { error(result,"update_required"); return; }
        if ("authState".equals(command)) { result.finish(state("state")); return; }
        if ("authToken".equals(command)) {
            FirebaseUser user = auth.getCurrentUser();
            String expected = payload.optString("uid", "");
            if (user == null || !user.getUid().equals(expected)) { error(result,"authentication_required"); return; }
            user.getIdToken(payload.optBoolean("forceRefresh", false)).addOnCompleteListener(activity, task -> {
                if (!task.isSuccessful() || auth.getCurrentUser() == null || !auth.getCurrentUser().getUid().equals(expected)) {
                    error(result,"authentication_required"); return;
                }
                try { result.finish(new JSONObject().put("uid", expected).put("token", task.getResult().getToken())); }
                catch (Exception ignored) { error(result,"authentication_required"); }
            });
            return;
        }
        if ("authSignOut".equals(command)) {
            auth.signOut();
            credentials.clearCredentialStateAsync(new ClearCredentialStateRequest(),null,activity::runOnUiThread,
                new CredentialManagerCallback<Void,ClearCredentialException>() {
                    public void onResult(Void ignored) { result.finish(state("signedOut")); }
                    public void onError(ClearCredentialException ignored) { result.finish(state("signedOut")); }
                });
            return;
        }
        if (!"authSignIn".equals(command) || signingIn) { error(result,"sign_in_unavailable"); return; }
        signingIn = true;
        boolean reauthenticate = payload.optBoolean("reauthenticate",false);
        String existingUid = auth.getCurrentUser() == null ? "" : auth.getCurrentUser().getUid();
        GetSignInWithGoogleOption option = new GetSignInWithGoogleOption.Builder(BuildConfig.GOOGLE_WEB_CLIENT_ID).build();
        GetCredentialRequest request = new GetCredentialRequest.Builder().addCredentialOption(option).build();
        cancellation = new CancellationSignal();
        credentials.getCredentialAsync(activity, request, cancellation, activity::runOnUiThread,
            new CredentialManagerCallback<GetCredentialResponse,GetCredentialException>() {
                public void onError(GetCredentialException ignored) { signingIn=false; error(result,"sign_in_canceled"); }
                public void onResult(GetCredentialResponse response) {
                    try {
                        Credential credential = response.getCredential();
                        if (!(credential instanceof CustomCredential) || !GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL.equals(credential.getType())) {
                            signingIn=false; error(result,"sign_in_unavailable"); return;
                        }
                        String token = GoogleIdTokenCredential.createFrom(((CustomCredential)credential).getData()).getIdToken();
                        com.google.firebase.auth.AuthCredential google = GoogleAuthProvider.getCredential(token,null);
                        if (reauthenticate) {
                            FirebaseUser current = auth.getCurrentUser();
                            if (current == null || !current.getUid().equals(existingUid)) { signingIn=false;error(result,"authentication_required");return; }
                            current.reauthenticate(google).addOnCompleteListener(activity,task -> {
                                signingIn=false;if(task.isSuccessful())result.finish(state("signedIn"));else error(result,"sign_in_unavailable");
                            });
                        } else {
                            auth.signInWithCredential(google).addOnCompleteListener(activity,task -> {
                                signingIn=false;if(task.isSuccessful())result.finish(state("signedIn"));else error(result,"sign_in_unavailable");
                            });
                        }
                    } catch (Exception ignored) { signingIn=false; error(result,"sign_in_unavailable"); }
                }
            });
    }
    void close() {
        if(cancellation != null)cancellation.cancel();
        if(auth != null && listener != null)auth.removeAuthStateListener(listener);
    }
}
