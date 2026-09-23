// Standalone preview of the bar item and popout in a floating window.
// Run via ../../preview.sh (optionally with AI_USAGE_MOCK=<scenario>).
import QtQuick
import Quickshell
import Caelestia.Config
import qs.components
import qs.services
import qs.aiusage

ShellRoot {
    FloatingWindow {
        title: "ai-usage preview"
        color: Colours.palette.m3surface
        implicitWidth: row.implicitWidth + Tokens.padding.large * 2
        implicitHeight: row.implicitHeight + Tokens.padding.large * 2

        Row {
            id: row

            anchors.centerIn: parent
            spacing: Tokens.padding.large

            StyledRect {
                implicitWidth: Tokens.sizes.bar.innerWidth + Tokens.padding.small * 2
                implicitHeight: item.implicitHeight + Tokens.padding.large * 2
                color: Colours.tPalette.m3surfaceContainer
                radius: Tokens.rounding.full

                AiUsageBar {
                    id: item

                    anchors.centerIn: parent
                }
            }

            StyledRect {
                implicitWidth: popout.width + Tokens.padding.large * 2
                implicitHeight: popout.implicitHeight + Tokens.padding.large * 2
                color: Colours.tPalette.m3surfaceContainer
                radius: Tokens.rounding.large

                AiUsagePopout {
                    id: popout

                    anchors.centerIn: parent
                }
            }
        }
    }
}
