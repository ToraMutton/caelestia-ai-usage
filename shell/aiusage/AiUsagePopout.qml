pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell
import Caelestia.Config
import qs.components
import qs.components.controls
import qs.services

// Detail popout: every window per provider with its reset countdown.
ColumnLayout {
    id: root

    spacing: Tokens.spacing.medium
    width: Tokens.sizes.bar.networkWidth

    RowLayout {
        Layout.fillWidth: true
        Layout.topMargin: Tokens.padding.small
        spacing: Tokens.spacing.small

        StyledText {
            Layout.fillWidth: true
            text: qsTr("AI usage")
            font: Tokens.font.body.builders.medium.weight(Font.Medium).build()
        }

        LoadingIndicator {
            visible: AiUsage.loading
            implicitSize: Math.round(Tokens.font.icon.medium.pointSize * 1.3)
        }

        IconButton {
            visible: !AiUsage.loading
            icon: "refresh"
            type: IconButton.Text
            onClicked: AiUsage.refresh(true)
        }
    }

    Repeater {
        model: ScriptModel {
            values: [AiUsage.claude, AiUsage.openai].filter(p => p)
        }

        Provider {}
    }

    StyledText {
        visible: !AiUsage.claude && !AiUsage.openai && !AiUsage.fetchError
        text: qsTr("Waiting for first update…")
        color: Colours.palette.m3onSurfaceVariant
        font: Tokens.font.body.small
    }

    StyledText {
        Layout.fillWidth: true
        visible: !!AiUsage.fetchError
        text: AiUsage.fetchError
        color: Colours.palette.m3error
        font: Tokens.font.body.small
        wrapMode: Text.Wrap
    }

    StyledText {
        Layout.bottomMargin: Tokens.padding.small
        text: AiUsage.loading ? qsTr("Updating…") : qsTr("Updated %1").arg(AiUsage.formatTime(AiUsage.updatedAt))
        color: Colours.palette.m3onSurfaceVariant
        font: Tokens.font.body.small
    }

    component Provider: ColumnLayout {
        id: section

        required property var modelData
        readonly property string status: AiUsage.statusText(modelData)

        Layout.fillWidth: true
        spacing: Tokens.spacing.small

        RowLayout {
            Layout.fillWidth: true
            spacing: Tokens.spacing.small

            StyledText {
                text: section.modelData.name
                font: Tokens.font.body.builders.medium.weight(Font.Medium).build()
                color: section.modelData.id === "claude" ? Colours.palette.m3primary : Colours.palette.m3tertiary
            }

            StyledRect {
                visible: !!section.modelData.plan
                implicitWidth: plan.implicitWidth + Tokens.padding.small * 2
                implicitHeight: plan.implicitHeight + Tokens.padding.extraSmall
                radius: Tokens.rounding.full
                color: Colours.palette.m3secondaryContainer

                StyledText {
                    id: plan

                    anchors.centerIn: parent
                    text: section.modelData.plan ?? ""
                    color: Colours.palette.m3onSecondaryContainer
                    font: Tokens.font.label.small
                }
            }

            Item {
                Layout.fillWidth: true
            }

            StyledText {
                visible: !!section.status
                text: section.status
                color: Colours.palette.m3error
                font: Tokens.font.body.small
            }
        }

        StyledText {
            Layout.fillWidth: true
            visible: !!section.modelData.shared_scope
            text: qsTr("Shared by %1").arg(section.modelData.shared_scope)
            color: Colours.palette.m3onSurfaceVariant
            font: Tokens.font.body.small
            elide: Text.ElideRight
        }

        Repeater {
            model: section.modelData.windows

            LimitRow {}
        }

        StyledText {
            Layout.fillWidth: true
            visible: !!section.modelData.error
            text: section.modelData.stale ? qsTr("%1 — showing data from %2").arg(section.modelData.error?.message).arg(AiUsage.formatTime(section.modelData.fetched_at)) : section.modelData.error?.message ?? ""
            color: Colours.palette.m3onSurfaceVariant
            font: Tokens.font.body.small
            wrapMode: Text.Wrap
        }
    }

    component LimitRow: ColumnLayout {
        id: win

        required property var modelData
        readonly property bool reset: AiUsage.isReset(modelData)
        readonly property real value: reset ? 0 : modelData.used_percent / 100

        Layout.fillWidth: true
        Layout.topMargin: Tokens.spacing.extraSmall
        spacing: Tokens.spacing.extraSmall

        RowLayout {
            Layout.fillWidth: true

            StyledText {
                Layout.fillWidth: true
                text: win.modelData.scope ? `${win.modelData.label} · ${win.modelData.scope}` : win.modelData.label
                font: Tokens.font.body.small
            }

            StyledText {
                text: win.reset ? "–" : `${Math.round(win.modelData.used_percent)}%`
                font: Tokens.font.body.builders.small.weight(Font.Medium).build()
                color: win.value >= 0.9 ? Colours.palette.m3error : Colours.palette.m3onSurface
            }
        }

        StyledProgressBar {
            Layout.fillWidth: true
            value: win.value
            fgColour: win.value >= 0.9 ? Colours.palette.m3error : Colours.palette.m3primary
        }

        StyledText {
            text: {
                const at = win.modelData.resets_at;
                if (!at)
                    return qsTr("Window not started");
                if (win.reset)
                    return qsTr("Reset at %1 — waiting for update").arg(AiUsage.formatTime(at));
                return qsTr("Resets in %1 · %2").arg(AiUsage.remaining(at)).arg(AiUsage.formatTime(at));
            }
            color: Colours.palette.m3onSurfaceVariant
            font: Tokens.font.body.small
        }
    }
}
