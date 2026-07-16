package com.torahpod.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.IBinder;

import java.io.IOException;

public class NativeAudioService extends Service {
    public static final String ACTION_PLAY = "com.torahpod.app.PLAY";
    public static final String ACTION_TOGGLE = "com.torahpod.app.TOGGLE";
    public static final String ACTION_STOP = "com.torahpod.app.STOP";
    public static final String EXTRA_URL = "url";
    public static final String EXTRA_TITLE = "title";
    public static final String EXTRA_SHOW = "show";
    public static final String EXTRA_ARTWORK = "artwork";

    private static final int NOTIFICATION_ID = 1042;
    private static final String CHANNEL_ID = "torah_pod_playback";

    private MediaPlayer player;
    private MediaSession mediaSession;
    private String currentTitle = "Torah Pod";
    private String currentShow = "";
    private String currentUrl = "";

    @Override
    public void onCreate() {
        super.onCreate();
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
        });
        mediaSession.setActive(true);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
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
        startForeground(NOTIFICATION_ID, buildNotification(false));
        releasePlayer();

        player = new MediaPlayer();
        try {
            if (Build.VERSION.SDK_INT >= 21) {
                player.setAudioAttributes(
                    new AudioAttributes.Builder()
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .build()
                );
            } else {
                player.setAudioStreamType(AudioManager.STREAM_MUSIC);
            }
            player.setDataSource(currentUrl);
            player.setOnPreparedListener(mp -> {
                mp.start();
                updatePlaybackState(true);
                startForeground(NOTIFICATION_ID, buildNotification(true));
            });
            player.setOnCompletionListener(mp -> stopPlayback());
            player.setOnErrorListener((mp, what, extra) -> {
                stopPlayback();
                return true;
            });
            player.prepareAsync();
            updatePlaybackState(false);
        } catch (IOException | IllegalArgumentException | IllegalStateException error) {
            stopPlayback();
        }
    }

    private void toggle() {
        if (player == null) {
            stopSelf();
            return;
        }
        if (player.isPlaying()) {
            pause();
        } else {
            resume();
        }
    }

    private void resume() {
        if (player == null) return;
        player.start();
        updatePlaybackState(true);
        startForeground(NOTIFICATION_ID, buildNotification(true));
    }

    private void pause() {
        if (player == null) return;
        player.pause();
        updatePlaybackState(false);
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.notify(NOTIFICATION_ID, buildNotification(false));
    }

    private void stopPlayback() {
        releasePlayer();
        updatePlaybackState(false);
        stopForeground(true);
        stopSelf();
    }

    private void releasePlayer() {
        if (player == null) return;
        try {
            player.reset();
            player.release();
        } catch (IllegalStateException ignored) {
        }
        player = null;
    }

    private void updatePlaybackState(boolean playing) {
        if (mediaSession == null) return;
        long actions = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_STOP;
        int state = playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED;
        mediaSession.setPlaybackState(
            new PlaybackState.Builder()
                .setActions(actions)
                .setState(state, PlaybackState.PLAYBACK_POSITION_UNKNOWN, 1.0f)
                .build()
        );
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
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .addAction(toggleAction)
            .addAction(stopAction)
            .setStyle(new Notification.MediaStyle()
                .setMediaSession(mediaSession.getSessionToken())
                .setShowActionsInCompactView(0));
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
        releasePlayer();
        if (mediaSession != null) {
            mediaSession.release();
            mediaSession = null;
        }
        super.onDestroy();
    }
}
