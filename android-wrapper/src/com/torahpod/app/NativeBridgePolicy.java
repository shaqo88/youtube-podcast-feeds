package com.torahpod.app;

import java.net.URI;

/** Pure-Java policy checks shared by the WebView bridge and its regression tests. */
final class NativeBridgePolicy {
    private static final String TRUSTED_HOST = "torah-pod.pages.dev";
    private static final int MAX_URL_LENGTH = 2048;
    private static final int MAX_TEXT_LENGTH = 300;

    private NativeBridgePolicy() {
    }

    static boolean isTrustedPage(String value) {
        return isTrustedPage(value, "https://" + TRUSTED_HOST);
    }

    static boolean isTrustedPage(String value, String origin) {
        try {
            URI uri = new URI(value);
            URI trusted = new URI(origin);
            int port = uri.getPort();
            return "https".equalsIgnoreCase(uri.getScheme())
                && "https".equalsIgnoreCase(trusted.getScheme())
                && uri.getUserInfo() == null && trusted.getUserInfo() == null
                && uri.getHost() != null && uri.getHost().equalsIgnoreCase(trusted.getHost())
                && (port == -1 || port == 443);
        } catch (Exception ignored) {
            return false;
        }
    }

    static boolean canReturnAuth(String caller, String current, String origin, int calledGeneration, int currentGeneration) {
        return calledGeneration == currentGeneration && isTrustedPage(caller, origin) && isTrustedPage(current, origin);
    }

    static boolean isHttpsUrl(String value, boolean required) {
        if (value == null || value.length() > MAX_URL_LENGTH) return false;
        if (!required && value.isEmpty()) return true;
        try {
            URI uri = new URI(value);
            return "https".equalsIgnoreCase(uri.getScheme())
                && uri.getHost() != null
                && uri.getUserInfo() == null;
        } catch (Exception ignored) {
            return false;
        }
    }

    static boolean isBoundedText(String value) {
        return value != null && value.length() <= MAX_TEXT_LENGTH;
    }
}
