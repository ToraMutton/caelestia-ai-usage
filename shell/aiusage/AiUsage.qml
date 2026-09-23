pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io
import qs.services

// Runs the `ai-usage` fetcher and exposes its normalized JSON.
// Countdowns are computed locally from resets_at, never by re-fetching.
Singleton {
    id: root

    readonly property string command: Quickshell.env("AI_USAGE_BIN") || `${Quickshell.env("HOME")}/.local/bin/ai-usage`
    // e.g. AI_USAGE_MOCK=partial_failure to preview the UI with mock data.
    readonly property list<string> mockArgs: Quickshell.env("AI_USAGE_MOCK") ? ["--mock", Quickshell.env("AI_USAGE_MOCK")] : []
    readonly property int interval: 5 * 60 * 1000
    readonly property int minRetry: 60 * 1000

    property list<var> providers: []
    readonly property bool loading: proc.running
    // The fetcher itself failed (not a per-provider error).
    property string fetchError
    property int retryDelay: minRetry

    readonly property var claude: providers.find(p => p.id === "claude") ?? null
    readonly property var openai: providers.find(p => p.id === "openai") ?? null
    // Newest time any provider's data was actually obtained.
    readonly property string updatedAt: providers.map(p => p.fetched_at).filter(t => t).sort().pop() ?? ""

    // `force` skips the fetcher's cache check (manual refresh, retries).
    function refresh(force: bool): void {
        if (proc.running)
            return;
        proc.command = [command, "--json", ...mockArgs, ...(force ? [] : ["--max-age", "240"])];
        proc.handled = false;
        proc.running = true;
    }

    // Used by the patched Bar.qml: insert our entry before the clock (or at the end).
    function withBarEntry(entries: var): var {
        const list = [...entries];
        const at = list.findIndex(e => e.id === "clock");
        list.splice(at === -1 ? list.length : at, 0, {
            id: "aiUsage",
            enabled: true
        });
        return list;
    }

    function windowOf(p: var, kind: string): var {
        return p?.windows.find(w => w.kind === kind && !w.scope) ?? null;
    }

    function isReset(w: var): bool {
        return !!w?.resets_at && new Date(w.resets_at) <= Time.date;
    }

    function remaining(iso: string): string {
        if (!iso)
            return "";
        const secs = Math.floor((new Date(iso) - Time.date) / 1000);
        if (secs <= 0)
            return qsTr("reset");
        const d = Math.floor(secs / 86400);
        const h = Math.floor(secs / 3600) % 24;
        const m = Math.floor(secs / 60) % 60;
        if (d > 0)
            return `${d}d ${h}h`;
        if (h > 0)
            return `${h}h ${m}m`;
        return m > 0 ? `${m}m` : "<1m";
    }

    function formatTime(iso: string): string {
        if (!iso)
            return "--:--";
        const date = new Date(iso);
        const sameDay = date.toDateString() === Time.date.toDateString();
        return Qt.formatDateTime(date, sameDay ? "hh:mm" : "M/d hh:mm");
    }

    function statusText(p: var): string {
        switch (p?.status) {
        case "ok":
            return "";
        case "auth_error":
            return qsTr("Not logged in");
        case "unsupported":
            return qsTr("No plan limits");
        case "not_installed":
            return qsTr("CLI not found");
        case "timeout":
            return qsTr("Timed out");
        case "not_fetched":
            return qsTr("Not fetched yet");
        default:
            return qsTr("Fetch failed");
        }
    }

    function apply(text: string): bool {
        let doc;
        try {
            doc = JSON.parse(text);
        } catch (e) {
            return false;
        }
        providers = doc.providers ?? [];
        fetchError = "";
        return true;
    }

    function scheduleRetry(): void {
        retryTimer.interval = retryDelay;
        retryTimer.restart();
        retryDelay = Math.min(retryDelay * 2, interval);
    }

    Component.onCompleted: cacheProc.running = true

    // Show the last cached result instantly on shell start, then fetch.
    Process {
        id: cacheProc

        command: [root.command, "--json", "--cached", ...root.mockArgs]
        stdout: StdioCollector {
            onStreamFinished: root.apply(text)
        }
        onRunningChanged: {
            if (!running)
                root.refresh(false);
        }
    }

    Process {
        id: proc

        property bool handled

        function checkHandled(): void {
            if (!handled) {
                handled = true;
                root.fetchError = qsTr("Could not run %1").arg(root.command);
                root.scheduleRetry();
            }
        }

        stdout: StdioCollector {
            onStreamFinished: {
                proc.handled = true;
                if (!root.apply(text)) {
                    root.fetchError = qsTr("ai-usage produced no valid output");
                    root.scheduleRetry();
                } else if (root.providers.some(p => p.status === "timeout" || p.status === "error")) {
                    // Transient provider failure: retry sooner. Auth problems won't fix themselves.
                    root.scheduleRetry();
                } else {
                    root.retryDelay = root.minRetry;
                }
            }
        }
        // No output at all means the fetcher couldn't even start. Deferred so a
        // stream that finishes in the same event loop pass is seen first.
        onRunningChanged: {
            if (!running)
                Qt.callLater(checkHandled);
        }
    }

    Timer {
        running: true
        repeat: true
        interval: root.interval
        onTriggered: root.refresh(false)
    }

    Timer {
        id: retryTimer

        onTriggered: root.refresh(true)
    }
}
