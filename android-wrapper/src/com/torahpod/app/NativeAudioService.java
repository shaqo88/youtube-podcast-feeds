package com.torahpod.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

import java.io.IOException;

public class NativeAudioService extends Service {
    public static final String ACTION_PLAY = "com.torahpod.app.PLAY";
    public static final String ACTION_TOGGLE = "com.torahpod.app.TOGGLE";
    public static final String ACTION_STOP = "com.torahpod.app.STOP";
    public static final String ACTION_SEEK_BY = "com.torahpod.app.SEEK_BY";
    public static final String ACTION_SEEK_TO = "com.torahpod.app.SEEK_TO";
    public static final String ACTION_PROGRESS = "com.torahpod.app.PROGRESS";
    public static final String ACTION_HTML_STATE = "com.torahpod.app.HTML_STATE";
    public static final String ACTION_HTML_STOP = "com.torahpod.app.HTML_STOP";
    public static final String ACTION_CONTROL = "com.torahpod.app.CONTROL";
    public static final String EXTRA_URL = "url";
    public static final String EXTRA_TITLE = "title";
    public static final String EXTRA_SHOW = "show";
    public static final String EXTRA_ARTWORK = "artwork";
    public static final String EXTRA_SECONDS = "seconds";
    public static final String EXTRA_POSITION = "position";
    public static final String EXTRA_DURATION = "duration";
    public static final String EXTRA_PLAYING = "playing";
    public static final String EXTRA_COMMAND = "command";

    private static final int NOTIFICATION_ID = 1042;
    private static final String CHANNEL_ID = "torah_pod_playback";

    private MediaPlayer player;
    private MediaSession mediaSession;
    private AudioManager audioManager;
    private AudioFocusRequest audioFocusRequest;
    private boolean hasAudioFocus = false;
    private boolean resumeOnAudioFocusGain = false;
    private boolean noisyReceiverRegistered = false;
    private int playbackGeneration = 0;
    private String currentTitle = "Torah Pod";
    private String currentShow = "";
    private String currentUrl = "";
    private boolean htmlNotificationMode = false;
    private boolean htmlPlaying = false;
    private int htmlPositionSeconds = 0;
    private int htmlDurationSeconds = 0;
    private final Handler progressHandler = new Handler(Looper.getMainLooper());
    private final AudioManager.OnAudioFocusChangeListener audioFocusChangeListener = focusChange -> {
        if (focusChange == AudioManager.AUDIOFOCUS_GAIN) {
            hasAudioFocus = true;
            if (resumeOnAudioFocusGain && player != null) {
                resumeOnAudioFocusGain = false;
                resume();
            }
        } else if (focusChange == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT
            || focusChange == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK) {
            pauseForAudioFocusLoss(true);
        } else if (focusChange == AudioManager.AUDIOFOCUS_LOSS) {
            pauseForAudioFocusLoss(false);
            abandonAudioFocus();
        }
    };
    private final BroadcastReceiver noisyReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (intent != null && AudioManager.ACTION_AUDIO_BECOMING_NOISY.equals(intent.getAction())) {
                resumeOnAudioFocusGain = false;
                pause();
            }
        }
    };
    private final Runnable progressRunnable = new Runnable() {
        @Override
        public void run() {
            sendProgress();
            if (player != null) {
                refreshNotification();
                progressHandler.postDelayed(this, 1000);
            }
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        audioManager = (AudioManager) getSystemService(AUDIO_SERVICE);
        registerNoisyReceiver();
        createNotificationChannel();
        mediaSession = new MediaSession(this, "Torah Pod");
        mediaSession.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                resume();
            }

            @Override
            public void onPause() {
                pause();
            }

            @Override
            public void onStop() {
                stopPlayback();
            }

            @Override
            public void onSeekTo(long pos) {
                seekToSeconds((int) Math.max(0, pos / 1000));
            }

            @Override
            public void onRewind() {
                seekBySeconds(-15);
            }

            @Override
            public void onFastForward() {
                seekBySeconds(30);
            }

            @Override
            public void onSkipToPrevious() {
                seekBySeconds(-15);
            }

            @Override
            public void onSkipToNext() {
                seekBySeconds(30);
            }
        });
        mediaSession.setActive(true);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        try {
            String action = intent != null ? intent.getAction() : "";
            if (ACTION_PLAY.equals(action)) {
                play(
                    intent.getStringExtra(EXTRA_URL),
                    intent.getStringExtra(EXTRA_TITLE),
                    intent.getStringExtra(EXTRA_SHOW)
                );
            } else if (ACTION_TOGGLE.equals(action)) {
                toggle();
            } else if (ACTION_STOP.equals(action)) {
                stopPlayback();
            } else if (ACTION_SEEK_BY.equals(action)) {
                seekBySeconds(intent.getIntExtra(EXTRA_SECONDS, 0));
            } else if (ACTION_SEEK_TO.equals(action)) {
                seekToSeconds(intent.getIntExtra(EXTRA_POSITION, 0));
            } else if (ACTION_HTML_STATE.equals(action)) {
                updateHtmlNotification(intent);
            } else if (ACTION_HTML_STOP.equals(action)) {
                stopHtmlNotification();
            }
        } catch (RuntimeException error) {
            stopPlayback();
        }
        return START_NOT_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void play(String url, String title, String show) {
        if (url == null || url.trim().isEmpty()) {
            stopSelf();
            return;
        }
        currentUrl = url;
        currentTitle = title == null || title.trim().isEmpty() ? "Torah Pod" : title;
        currentShow = show == null ? "" : show;
        htmlNotificationMode = false;
        int generation = ++playbackGeneration;
        startForeground(NOTIFICATION_ID, buildNotification(false));
        releasePlayer();

        MediaPlayer nextPlayer = new MediaPlayer();
        try {
            if (Build.VERSION.SDK_INT >= 21) {
            nextPlayer.setAudioAttributes(
                    playbackAudioAttributes()
                );
            } else {
                nextPlayer.setAudioStreamType(AudioManager.STREAM_MUSIC);
            }
            nextPlayer.setDataSource(currentUrl);
            nextPlayer.setOnPreparedListener(mp -> {
                if (!isCurrentPlayer(mp, generation)) return;
                if (!requestAudioFocus()) {
                    stopPlayback();
                    return;
                }
                try {
                    mp.start();
                } catch (IllegalStateException ignored) {
                    return;
                }
                updatePlaybackState(true);
                startProgressUpdates();
                sendProgress();
                startForeground(NOTIFICATION_ID, buildNotification(true));
            });
            nextPlayer.setOnCompletionListener(mp -> {
                if (isCurrentPlayer(mp, generation)) {
                    sendHtmlControl("ended");
                    stopPlayback();
                }
            });
            nextPlayer.setOnErrorListener((mp, what, extra) -> {
                if (isCurrentPlayer(mp, generation)) {
                    stopPlayback();
                }
                return true;
            });
            player = nextPlayer;
            nextPlayer.prepareAsync();
            updatePlaybackState(false);
            sendProgress();
        } catch (IOException | RuntimeException error) {
            try {
                nextPlayer.release();
            } catch (RuntimeException ignored) {
            }
            stopPlayback();
        }
    }

    private boolean isCurrentPlayer(MediaPlayer candidate, int generation) {
        return candidate != null && candidate == player && generation == playbackGeneration;
    }

    private void toggle() {
        if (htmlNotificationMode) {
            sendHtmlControl("toggle");
            return;
        }
        if (player == null) {
            stopSelf();
            return;
        }
        if (safeIsPlaying()) {
            pause();
        } else {
            resume();
        }
    }

    private void resume() {
        if (htmlNotificationMode) {
            sendHtmlControl("play");
            return;
        }
        if (player == null) return;
        if (!requestAudioFocus()) return;
        try {
            player.start();
        } catch (IllegalStateException ignored) {
            return;
        }
        updatePlaybackState(true);
        startProgressUpdates();
        sendProgress();
        startForeground(NOTIFICATION_ID, buildNotification(true));
    }

    private void pause() {
        if (htmlNotificationMode) {
            sendHtmlControl("pause");
            return;
        }
        resumeOnAudioFocusGain = false;
        pauseNativePlayback();
        abandonAudioFocus();
    }

    private void pauseNativePlayback() {
        if (player == null || !safeIsPlaying()) return;
        try {
            player.pause();
        } catch (IllegalStateException ignored) {
            return;
        }
        updatePlaybackState(false);
        stopProgressUpdates();
        sendProgress();
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.notify(NOTIFICATION_ID, buildNotification(false));
    }

    private void pauseForAudioFocusLoss(boolean resumeAfterGain) {
        boolean wasPlaying = safeIsPlaying();
        resumeOnAudioFocusGain = resumeAfterGain && wasPlaying;
        if (wasPlaying) {
            pauseNativePlayback();
        }
    }

    private void stopPlayback() {
        if (htmlNotificationMode) {
            sendHtmlControl("stop");
            stopHtmlNotification();
            return;
        }
        resumeOnAudioFocusGain = false;
        abandonAudioFocus();
        sendStoppedProgress();
        releasePlayer();
        updatePlaybackState(false);
        stopForeground(true);
        stopSelf();
    }

    private void releasePlayer() {
        if (player == null) return;
        stopProgressUpdates();
        MediaPlayer oldPlayer = player;
        player = null;
        try {
            oldPlayer.setOnPreparedListener(null);
            oldPlayer.setOnCompletionListener(null);
            oldPlayer.setOnErrorListener(null);
            oldPlayer.release();
        } catch (RuntimeException ignored) {
        }
    }

    private AudioAttributes playbackAudioAttributes() {
        return new AudioAttributes.Builder()
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .build();
    }

    @SuppressWarnings("deprecation")
    private boolean requestAudioFocus() {
        if (hasAudioFocus) return true;
        if (audioManager == null) return false;
        int result;
        if (Build.VERSION.SDK_INT >= 26) {
            if (audioFocusRequest == null) {
                audioFocusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                    .setAudioAttributes(playbackAudioAttributes())
                    .setOnAudioFocusChangeListener(audioFocusChangeListener)
                    .setWillPauseWhenDucked(true)
                    .build();
            }
            result = audioManager.requestAudioFocus(audioFocusRequest);
        } else {
            result = audioManager.requestAudioFocus(
                audioFocusChangeListener,
                AudioManager.STREAM_MUSIC,
                AudioManager.AUDIOFOCUS_GAIN
            );
        }
        hasAudioFocus = result == AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
        return hasAudioFocus;
    }

    @SuppressWarnings("deprecation")
    private void abandonAudioFocus() {
        if (!hasAudioFocus || audioManager == null) return;
        if (Build.VERSION.SDK_INT >= 26 && audioFocusRequest != null) {
            audioManager.abandonAudioFocusRequest(audioFocusRequest);
        } else {
            audioManager.abandonAudioFocus(audioFocusChangeListener);
        }
        hasAudioFocus = false;
    }

    private void registerNoisyReceiver() {
        if (noisyReceiverRegistered) return;
        IntentFilter filter = new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(noisyReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(noisyReceiver, filter);
        }
        noisyReceiverRegistered = true;
    }

    private void unregisterNoisyReceiver() {
        if (!noisyReceiverRegistered) return;
        try {
            unregisterReceiver(noisyReceiver);
        } catch (IllegalArgumentException ignored) {
        }
        noisyReceiverRegistered = false;
    }

    private void updateHtmlNotification(Intent intent) {
        resumeOnAudioFocusGain = false;
        abandonAudioFocus();
        releasePlayer();
        htmlNotificationMode = true;
        currentUrl = intent.getStringExtra(EXTRA_URL);
        currentTitle = intent.getStringExtra(EXTRA_TITLE);
        if (currentTitle == null || currentTitle.trim().isEmpty()) {
            currentTitle = "Torah Pod";
        }
        currentShow = intent.getStringExtra(EXTRA_SHOW);
        if (currentShow == null) {
            currentShow = "";
        }
        htmlPositionSeconds = Math.max(0, intent.getIntExtra(EXTRA_POSITION, 0));
        htmlDurationSeconds = Math.max(0, intent.getIntExtra(EXTRA_DURATION, 0));
        htmlPlaying = intent.getBooleanExtra(EXTRA_PLAYING, false);
        updatePlaybackState(htmlPlaying);
        startForeground(NOTIFICATION_ID, buildNotification(htmlPlaying));
    }

    private void stopHtmlNotification() {
        resumeOnAudioFocusGain = false;
        abandonAudioFocus();
        htmlNotificationMode = false;
        htmlPlaying = false;
        htmlPositionSeconds = 0;
        htmlDurationSeconds = 0;
        updatePlaybackState(false);
        stopForeground(true);
        stopSelf();
    }

    private void sendHtmlControl(String command) {
        Intent intent = new Intent(ACTION_CONTROL);
        intent.setPackage(getPackageName());
        intent.putExtra(EXTRA_COMMAND, command);
        sendBroadcast(intent);
    }

    private void seekBySeconds(int deltaSeconds) {
        if (htmlNotificationMode) return;
        if (player == null || deltaSeconds == 0) return;
        seekToSeconds(safePositionSeconds() + deltaSeconds);
    }

    private void seekToSeconds(int seconds) {
        if (htmlNotificationMode) return;
        if (player == null) return;
        int duration = safeDurationSeconds();
        int target = Math.max(0, seconds);
        if (duration > 0) {
            target = Math.min(target, duration);
        }
        try {
            player.seekTo(target * 1000);
            updatePlaybackState(safeIsPlaying());
            sendProgress();
        } catch (IllegalStateException ignored) {
        }
    }

    private int safePositionSeconds() {
        if (htmlNotificationMode) return htmlPositionSeconds;
        if (player == null) return 0;
        try {
            return Math.max(0, player.getCurrentPosition() / 1000);
        } catch (IllegalStateException ignored) {
            return 0;
        }
    }

    private int safeDurationSeconds() {
        if (htmlNotificationMode) return htmlDurationSeconds;
        if (player == null) return 0;
        try {
            int duration = player.getDuration();
            return duration > 0 ? duration / 1000 : 0;
        } catch (IllegalStateException ignored) {
            return 0;
        }
    }

    private boolean safeIsPlaying() {
        if (htmlNotificationMode) return htmlPlaying;
        if (player == null) return false;
        try {
            return player.isPlaying();
        } catch (IllegalStateException ignored) {
            return false;
        }
    }

    private void startProgressUpdates() {
        progressHandler.removeCallbacks(progressRunnable);
        progressHandler.post(progressRunnable);
    }

    private void stopProgressUpdates() {
        progressHandler.removeCallbacks(progressRunnable);
    }

    private void sendProgress() {
        Intent intent = new Intent(ACTION_PROGRESS);
        intent.setPackage(getPackageName());
        intent.putExtra(EXTRA_POSITION, safePositionSeconds());
        intent.putExtra(EXTRA_DURATION, safeDurationSeconds());
        intent.putExtra(EXTRA_PLAYING, safeIsPlaying());
        sendBroadcast(intent);
    }

    private void refreshNotification() {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager != null && (player != null || htmlNotificationMode)) {
            manager.notify(NOTIFICATION_ID, buildNotification(safeIsPlaying()));
        }
    }

    private void sendStoppedProgress() {
        Intent intent = new Intent(ACTION_PROGRESS);
        intent.setPackage(getPackageName());
        intent.putExtra(EXTRA_POSITION, 0);
        intent.putExtra(EXTRA_DURATION, 0);
        intent.putExtra(EXTRA_PLAYING, false);
        sendBroadcast(intent);
    }

    private void updatePlaybackState(boolean playing) {
        if (mediaSession == null) return;
        long actions = PlaybackState.ACTION_PLAY
            | PlaybackState.ACTION_PAUSE
            | PlaybackState.ACTION_PLAY_PAUSE
            | PlaybackState.ACTION_STOP
            | PlaybackState.ACTION_SEEK_TO
            | PlaybackState.ACTION_REWIND
            | PlaybackState.ACTION_FAST_FORWARD
            | PlaybackState.ACTION_SKIP_TO_PREVIOUS
            | PlaybackState.ACTION_SKIP_TO_NEXT;
        int state = playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED;
        mediaSession.setPlaybackState(
            new PlaybackState.Builder()
                .setActions(actions)
                .setState(state, safePositionSeconds() * 1000L, 1.0f)
                .build()
        );
        MediaMetadata.Builder metadata = new MediaMetadata.Builder()
            .putString(MediaMetadata.METADATA_KEY_TITLE, currentTitle)
            .putString(MediaMetadata.METADATA_KEY_ARTIST, currentShow);
        int duration = safeDurationSeconds();
        if (duration > 0) {
            metadata.putLong(MediaMetadata.METADATA_KEY_DURATION, duration * 1000L);
        }
        mediaSession.setMetadata(metadata.build());
    }

    private Notification buildNotification(boolean playing) {
        Intent contentIntent = new Intent(this, MainActivity.class);
        PendingIntent contentPendingIntent = PendingIntent.getActivity(
            this,
            0,
            contentIntent,
            pendingIntentFlags()
        );

        PendingIntent toggleIntent = PendingIntent.getService(
            this,
            1,
            new Intent(this, NativeAudioService.class).setAction(ACTION_TOGGLE),
            pendingIntentFlags()
        );
        PendingIntent stopIntent = PendingIntent.getService(
            this,
            2,
            new Intent(this, NativeAudioService.class).setAction(ACTION_STOP),
            pendingIntentFlags()
        );
        PendingIntent rewindIntent = PendingIntent.getService(
            this,
            3,
            new Intent(this, NativeAudioService.class)
                .setAction(ACTION_SEEK_BY)
                .putExtra(EXTRA_SECONDS, -15),
            pendingIntentFlags()
        );
        PendingIntent forwardIntent = PendingIntent.getService(
            this,
            4,
            new Intent(this, NativeAudioService.class)
                .setAction(ACTION_SEEK_BY)
                .putExtra(EXTRA_SECONDS, 30),
            pendingIntentFlags()
        );

        Notification.Action toggleAction = new Notification.Action.Builder(
            playing ? android.R.drawable.ic_media_pause : android.R.drawable.ic_media_play,
            playing ? "Pause" : "Play",
            toggleIntent
        ).build();
        Notification.Action stopAction = new Notification.Action.Builder(
            android.R.drawable.ic_menu_close_clear_cancel,
            "Stop",
            stopIntent
        ).build();
        Notification.Action rewindAction = new Notification.Action.Builder(
            android.R.drawable.ic_media_rew,
            "Back 15 seconds",
            rewindIntent
        ).build();
        Notification.Action forwardAction = new Notification.Action.Builder(
            android.R.drawable.ic_media_ff,
            "Forward 30 seconds",
            forwardIntent
        ).build();

        int position = safePositionSeconds();
        int duration = safeDurationSeconds();

        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new Notification.Builder(this, CHANNEL_ID)
            : new Notification.Builder(this);
        builder
            .setSmallIcon(R.drawable.icon)
            .setContentTitle(currentTitle)
            .setContentText(currentShow)
            .setContentIntent(contentPendingIntent)
            .setOngoing(playing)
            .setOnlyAlertOnce(true)
            .setVisibility(Notification.VISIBILITY_PUBLIC);
        Notification.MediaStyle mediaStyle = new Notification.MediaStyle()
            .setMediaSession(mediaSession.getSessionToken());
        if (htmlNotificationMode) {
            builder.addAction(toggleAction)
                .addAction(stopAction)
                .setStyle(mediaStyle.setShowActionsInCompactView(0));
        } else {
            builder.addAction(rewindAction)
                .addAction(toggleAction)
                .addAction(forwardAction)
                .addAction(stopAction)
                .setStyle(mediaStyle.setShowActionsInCompactView(0, 1, 2));
        }
        if (duration > 0) {
            builder.setProgress(duration, Math.min(position, duration), false);
        }
        if (playing) {
            builder.setWhen(System.currentTimeMillis() - position * 1000L)
                .setShowWhen(true)
                .setUsesChronometer(true);
        } else {
            builder.setShowWhen(false)
                .setUsesChronometer(false);
        }
        return builder.build();
    }

    private int pendingIntentFlags() {
        return Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT : PendingIntent.FLAG_UPDATE_CURRENT;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Torah Pod playback",
            NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("Playback controls for Torah Pod");
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(channel);
    }

    @Override
    public void onDestroy() {
        unregisterNoisyReceiver();
        resumeOnAudioFocusGain = false;
        abandonAudioFocus();
        stopProgressUpdates();
        releasePlayer();
        if (mediaSession != null) {
            mediaSession.release();
            mediaSession = null;
        }
        super.onDestroy();
    }
}
