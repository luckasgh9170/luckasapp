import QtQuick
import QtQuick.Layouts

Rectangle {
    id: panel
    property string title: ""
    property color themePanel: "#1a1d24"
    property color themeText: "#f5f7fb"
    property color themeMuted: "#9ba4b5"
    property Component content

    Layout.fillWidth: true
    implicitHeight: body.implicitHeight + 34
    radius: 22
    color: themePanel
    border.color: "#2a3140"

    ColumnLayout {
        id: body
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        Text {
            Layout.fillWidth: true
            text: panel.title
            color: themeText
            font.pixelSize: 18
            font.bold: true
            elide: Text.ElideRight
        }

        Loader {
            Layout.fillWidth: true
            sourceComponent: panel.content
        }
    }
}
