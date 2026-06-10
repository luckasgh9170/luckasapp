import QtQuick
import QtQuick.Layouts

RowLayout {
    id: bars
    property var items: []
    property color barColor: "#53d6a2"
    property color mutedColor: "#9ba4b5"

    spacing: 6

    Repeater {
        model: items
        delegate: ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 120
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: Math.max(4, parent.height * ((modelData.total || 0) / Math.max(1, bars.maxValue())))
                    radius: 4
                    color: barColor
                }
            }

            Text {
                Layout.fillWidth: true
                text: (modelData.label || "").slice(-5)
                color: mutedColor
                font.pixelSize: 10
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
        }
    }

    function maxValue() {
        var value = 1
        if (!items)
            return value
        for (var i = 0; i < items.length; i++)
            value = Math.max(value, items[i].total || 0)
        return value
    }
}
