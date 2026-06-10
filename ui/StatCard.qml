import QtQuick
import QtQuick.Layouts

Rectangle {
    id: card
    property string title: ""
    property string value: ""
    property color accent: "#53d6a2"

    Layout.fillWidth: true
    Layout.preferredHeight: 112
    radius: 24
    color: "#1a1d24"
    border.color: "#2a3140"

    Behavior on scale { NumberAnimation { duration: 140 } }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onEntered: card.scale = 1.025
        onExited: card.scale = 1
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 8

        Rectangle {
            width: 38
            height: 5
            radius: 3
            color: accent
        }

        Text {
            text: title
            color: "#9ba4b5"
            font.pixelSize: 13
        }

        Text {
            text: value
            color: "#f5f7fb"
            font.pixelSize: 25
            font.bold: true
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
    }
}
