pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Caelestia.Config
import qs.components
import qs.components.controls
import qs.services

// Compact bar entry: one double ring per provider (outer = short window,
// inner = weekly), with the short-window percentage in the middle.
// Hovering opens the "aiusage" popout via Bar.checkPopout (see shell/patches).
StyledRect {
    id: root

    implicitWidth: Tokens.sizes.bar.innerWidth
    implicitHeight: layout.implicitHeight + Tokens.padding.small * 2

    color: "transparent"
    radius: Tokens.rounding.full

    ColumnLayout {
        id: layout

        anchors.centerIn: parent
        spacing: Tokens.spacing.small

        Gauge {
            provider: AiUsage.claude
            colour: Colours.palette.m3primary
        }

        Gauge {
            provider: AiUsage.openai
            colour: Colours.palette.m3tertiary
        }
    }

    component Gauge: Item {
        id: gauge

        required property var provider
        required property color colour

        readonly property var short: AiUsage.windowOf(provider, "short")
        readonly property var weekly: AiUsage.windowOf(provider, "weekly")
        readonly property bool hasData: !!short || !!weekly
        readonly property real shortVal: short && !AiUsage.isReset(short) ? short.used_percent / 100 : 0
        readonly property real weeklyVal: weekly && !AiUsage.isReset(weekly) ? weekly.used_percent / 100 : 0
        readonly property color fg: Math.max(shortVal, weeklyVal) >= 0.9 ? Colours.palette.m3error : colour
        readonly property real size: Tokens.sizes.bar.innerWidth - Tokens.padding.small * 2

        Layout.alignment: Qt.AlignHCenter
        implicitWidth: size
        implicitHeight: size
        // Stale data (last fetch failed) is dimmed rather than hidden.
        opacity: provider?.stale ? 0.5 : 1

        CircularProgress {
            anchors.fill: parent
            visible: gauge.hasData
            value: gauge.shortVal
            strokeWidth: Math.max(2, Math.round(gauge.size / 11))
            fgColour: gauge.fg

            Behavior on clampedVal {
                Anim {}
            }
        }

        CircularProgress {
            anchors.fill: parent
            anchors.margins: Math.round(gauge.size / 6)
            visible: gauge.hasData
            value: gauge.weeklyVal
            strokeWidth: Math.max(1, Math.round(gauge.size / 16))
            fgColour: Qt.alpha(gauge.fg, 0.7)

            Behavior on clampedVal {
                Anim {}
            }
        }

        StyledText {
            anchors.centerIn: parent
            visible: gauge.hasData
            text: gauge.short && !AiUsage.isReset(gauge.short) ? Math.round(gauge.short.used_percent) : "–"
            font: Tokens.font.label.builders.small.scale(0.8).build()
            color: gauge.fg
        }

        MaterialIcon {
            anchors.centerIn: parent
            visible: !gauge.hasData
            readonly property bool waiting: !AiUsage.fetchError && (!gauge.provider || gauge.provider.status === "not_fetched")

            text: waiting ? "hourglass_empty" : gauge.provider?.status === "auth_error" ? "key_off" : "error"
            color: waiting ? Colours.palette.m3onSurfaceVariant : Colours.palette.m3error
        }
    }
}
