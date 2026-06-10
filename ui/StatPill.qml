import QtQuick
import QtQuick.Layouts

Rectangle {
    property string label: ""
    property string value: ""
    property color accent: "#53d6a2"

    width: 86
    height: 58
    radius: 14
    color: "#11141b"
    border.color: "#2a3140"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 2

        Text {
            Layout.fillWidth: true
            text: label
            color: "#9ba4b5"
            font.pixelSize: 11
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }

        Text {
            Layout.fillWidth: true
            text: value
            color: accent
            font.pixelSize: 16
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
    }
}
