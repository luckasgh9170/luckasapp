import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: card
    property var item
    signal connectClicked()
    signal disconnectClicked()
    signal testClicked()
    signal copyClicked()
    signal favoriteClicked()
    signal exportClicked()
    signal detailsClicked()
    signal deleteClicked()

    Layout.preferredHeight: 238
    radius: 20
    color: "#1b202b"
    border.color: item.ready ? "#2f7458" : "#303948"
    clip: true

    function statusColor(status) {
        if (status === "healthy" || status === "working" || status === "online")
            return "#163728"
        if (status === "slow")
            return "#463b1c"
        if (status === "testing")
            return "#193255"
        if (status === "unknown")
            return "#2b313d"
        return "#4a2430"
    }

    function flagText(country) {
        if (!country || country === "Unknown")
            return "--"
        return country.substring(0, 2).toUpperCase()
    }

    function pingText() {
        if (item.ping_ms)
            return item.ping_ms + " ms"
        return "--"
    }

    Behavior on scale { NumberAnimation { duration: 120 } }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        onEntered: card.scale = 1.012
        onExited: card.scale = 1
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Rectangle {
                width: 48
                height: 48
                radius: 16
                color: "#242b37"
                border.color: "#303948"
                Text {
                    anchors.centerIn: parent
                    text: flagText(item.country)
                    color: "#42d392"
                    font.bold: true
                    font.pixelSize: 14
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                Text {
                    Layout.fillWidth: true
                    text: item.name || "Unnamed server"
                    color: "#f7f9fc"
                    font.pixelSize: 16
                    font.bold: true
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    text: (item.host || "") + ":" + (item.port || "")
                    color: "#9aa5b5"
                    font.pixelSize: 12
                    elide: Text.ElideMiddle
                }
            }

            Rectangle {
                width: 86
                height: 30
                radius: 15
                color: statusColor(item.status)
                border.color: "#303948"
                Text {
                    anchors.centerIn: parent
                    width: parent.width - 10
                    text: item.ready ? "Ready" : (item.status || "Unknown")
                    color: "#f7f9fc"
                    font.pixelSize: 12
                    font.bold: true
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 3
            columnSpacing: 10
            rowSpacing: 8

            StatPill { label: "Protocol"; value: (item.protocol || "").toUpperCase(); accent: "#62a8ff" }
            StatPill { label: "Ping"; value: pingText(); accent: item.ready ? "#42d392" : "#ffca62" }
            StatPill { label: "Score"; value: Math.round(item.score || 0); accent: "#42d392" }
        }

        Text {
            Layout.fillWidth: true
            text: (item.country || "Unknown") + "  -  " + (item.quality || "Poor") + "  -  " + (item.last_check_at || "Never")
            color: "#9aa5b5"
            font.pixelSize: 12
            elide: Text.ElideRight
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Button {
                Layout.fillWidth: true
                text: "Connect"
                enabled: item.ready
                onClicked: card.connectClicked()
            }
            Button {
                Layout.fillWidth: true
                text: "Copy"
                onClicked: card.copyClicked()
            }
            Button {
                Layout.fillWidth: true
                text: item.favorite ? "Saved" : "Favorite"
                onClicked: card.favoriteClicked()
            }
            Button {
                Layout.fillWidth: true
                text: "Details"
                onClicked: card.detailsClicked()
            }
        }
    }
}
