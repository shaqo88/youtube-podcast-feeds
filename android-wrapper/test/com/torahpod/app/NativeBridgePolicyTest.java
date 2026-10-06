package com.torahpod.app;

public final class NativeBridgePolicyTest {
    private static int assertions = 0;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        check(NativeBridgePolicy.isTrustedPage("https://torah-pod.pages.dev/"), "trusted root");
        check(NativeBridgePolicy.isTrustedPage("https://torah-pod.pages.dev:443/onboard/"), "trusted default port");
        check(!NativeBridgePolicy.isTrustedPage("http://torah-pod.pages.dev/"), "http rejected");
        check(!NativeBridgePolicy.isTrustedPage("https://evil.example/?torah-pod.pages.dev"), "untrusted host rejected");
        check(!NativeBridgePolicy.isTrustedPage("https://torah-pod.pages.dev.evil.example/"), "lookalike host rejected");
        check(!NativeBridgePolicy.isTrustedPage("https://torah-pod.pages.dev:8443/"), "non-default port rejected");

        check(NativeBridgePolicy.isHttpsUrl("https://media.example/episode.mp3", true), "HTTPS media accepted");
        check(NativeBridgePolicy.isHttpsUrl("", false), "optional artwork omitted");
        check(!NativeBridgePolicy.isHttpsUrl("http://media.example/episode.mp3", true), "HTTP media rejected");
        check(!NativeBridgePolicy.isHttpsUrl("https:episode.mp3", true), "hostless URL rejected");
        check(!NativeBridgePolicy.isHttpsUrl("https://user:pass@media.example/episode.mp3", true), "credential URL rejected");
        check(NativeBridgePolicy.isBoundedText("Torah Pod"), "short text accepted");
        check(!NativeBridgePolicy.isBoundedText(new String(new char[301]).replace('\0', 'x')), "oversized text rejected");

        check(!NativeBridgePolicy.isTrustedPage("https://user@torah-pod.pages.dev/"), "credential-bearing page rejected");
        check(NativeBridgePolicy.canReturnAuth("https://torah-pod.pages.dev/account/", "https://torah-pod.pages.dev/", "https://torah-pod.pages.dev", 1, 1), "trusted async reply");
        check(!NativeBridgePolicy.canReturnAuth("https://evil.example/", "https://torah-pod.pages.dev/", "https://torah-pod.pages.dev", 1, 1), "untrusted caller rejected");
        check(!NativeBridgePolicy.canReturnAuth("https://torah-pod.pages.dev/", "https://evil.example/", "https://torah-pod.pages.dev", 1, 1), "untrusted current page rejected");
        check(!NativeBridgePolicy.canReturnAuth("https://torah-pod.pages.dev/", "https://torah-pod.pages.dev/", "https://torah-pod.pages.dev", 1, 2), "reply after document navigation rejected");
        check(NativeBridgePolicy.isTrustedPage("https://accounts-preview.torah-pod.pages.dev/", "https://accounts-preview.torah-pod.pages.dev"), "exact preview origin allowed");
        check(!NativeBridgePolicy.isTrustedPage("https://torah-pod.pages.dev/", "https://accounts-preview.torah-pod.pages.dev"), "production page rejected by preview");
        System.out.println("NativeBridgePolicyTest passed " + assertions + " checks.");
    }
}
