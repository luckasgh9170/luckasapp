import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1280
    height: 820
    minimumWidth: 640
    minimumHeight: 620
    visible: true
    title: "LuckasApp"
    color: theme.bg

    QtObject {
        id: theme
        property color bg: "#0f1117"
        property color sidebar: "#141821"
        property color panel: "#1b202b"
        property color panel2: "#242b37"
        property color line: "#303948"
        property color text: "#f7f9fc"
        property color muted: "#9aa5b5"
        property color green: "#42d392"
        property color blue: "#62a8ff"
        property color amber: "#ffca62"
        property color red: "#ff6b7a"
    }

    property bool compact: width < 960
    property bool narrow: width < 760
    property string currentPage: "Dashboard"
    property string toast: "Ready"
    property string searchText: ""
    property var configs: []
    property var favorites: []
    property var stats: ({})
    property var traffic: ({ speedPoints: [], daily: [], weekly: [], monthly: [] })
    property var settings: ({})
    property var sync: ({})
    property var update: ({})
    property var service: ({})
    property var diagnostics: ({})
    property var navItems: ["Dashboard", "Nodes", "Quick Connect", "Statistics", "Settings"]

    function reloadAll() {
        configs = appBridge.configList()
        favorites = appBridge.favoriteList()
        stats = appBridge.stats()
        traffic = appBridge.trafficStats()
        settings = appBridge.appSettings()
        sync = appBridge.syncStatus()
        update = appBridge.updateStatus()
        service = appBridge.serviceStatus()
        diagnostics = appBridge.diagnosticsStatus()
        applyTheme(settings.theme || "dark")
    }

    function refreshLive() {
        stats = appBridge.stats()
        traffic = appBridge.trafficStats()
        service = appBridge.serviceStatus()
        diagnostics = appBridge.diagnosticsStatus()
    }

    function filtered(list) {
        var source = list || []
        if (!searchText)
            return source
        var text = searchText.toLowerCase()
        return source.filter(function(item) {
            return (item.name || "").toLowerCase().indexOf(text) >= 0
                || (item.host || "").toLowerCase().indexOf(text) >= 0
                || (item.protocol || "").toLowerCase().indexOf(text) >= 0
                || (item.country || "").toLowerCase().indexOf(text) >= 0
        })
    }

    function bestNode() {
        return configs && configs.length ? configs[0] : ({})
    }

    function bestLatency() {
        var node = bestNode()
        return node.ping_ms ? node.ping_ms + " ms" : "--"
    }

    function quickActionText() {
        if (appBridge.connectionStatus === "Connecting" || appBridge.connectionStatus === "Verifying" || appBridge.connectionStatus === "Reconnecting")
            return appBridge.connectionStatus
        if (appBridge.connectionStatus === "Connected")
            return "Disconnect"
        return "Connect"
    }

    function quickAction() {
        if (appBridge.connectionStatus === "Connected")
            appBridge.disconnect()
        else
            appBridge.smartConnect()
    }

    function applyTheme(mode) {
        if (mode === "light") {
            theme.bg = "#f5f7fb"
            theme.sidebar = "#ffffff"
            theme.panel = "#ffffff"
            theme.panel2 = "#e9eef6"
            theme.line = "#d9e1ec"
            theme.text = "#10131a"
            theme.muted = "#657085"
        } else {
            theme.bg = "#0f1117"
            theme.sidebar = "#141821"
            theme.panel = "#1b202b"
            theme.panel2 = "#242b37"
            theme.line = "#303948"
            theme.text = "#f7f9fc"
            theme.muted = "#9aa5b5"
        }
    }

    function setTheme(mode) {
        applyTheme(mode)
        appBridge.setSetting("theme", mode)
    }

    Component.onCompleted: reloadAll()

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: refreshLive()
    }

    Connections {
        target: appBridge
        function onConfigsChanged() { configs = appBridge.configList(); favorites = appBridge.favoriteList() }
        function onStatsChanged() { stats = appBridge.stats(); diagnostics = appBridge.diagnosticsStatus(); service = appBridge.serviceStatus() }
        function onTrafficChanged() { traffic = appBridge.trafficStats() }
        function onSettingsChanged() { settings = appBridge.appSettings(); applyTheme(settings.theme || "dark") }
        function onSyncChanged() { sync = appBridge.syncStatus(); configs = appBridge.configList() }
        function onUpdateChanged() { update = appBridge.updateStatus() }
        function onCurrentServerChanged() { stats = appBridge.stats() }
        function onConnectionModeChanged() { stats = appBridge.stats(); diagnostics = appBridge.diagnosticsStatus() }
        function onNotification(message) { toast = message }
    }

    component AppButton: Button {
        id: control
        property color fill: theme.panel2
        property color ink: theme.text
        property int corner: 14
        implicitHeight: 42
        font.pixelSize: 13
        font.bold: true
        background: Rectangle {
            radius: control.corner
            color: !control.enabled ? "#252a34" : (control.down ? Qt.darker(control.fill, 1.12) : (control.hovered ? Qt.lighter(control.fill, 1.08) : control.fill))
            border.color: theme.line
        }
        contentItem: Text {
            text: control.text
            color: control.enabled ? control.ink : theme.muted
            font: control.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    component InfoLine: RowLayout {
        property string label: ""
        property string value: ""
        Layout.fillWidth: true
        spacing: 10
        Text {
            text: label
            color: theme.muted
            font.pixelSize: 12
            Layout.preferredWidth: 132
            elide: Text.ElideRight
        }
        Text {
            text: value
            color: theme.text
            font.pixelSize: 13
            font.bold: true
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
    }

    component ToggleLine: RowLayout {
        property string label: ""
        property string settingKey: ""
        property bool currentValue: false
        Layout.fillWidth: true
        Text {
            text: label
            color: theme.text
            font.pixelSize: 13
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
        Switch {
            checked: currentValue
            onToggled: appBridge.setSetting(settingKey, checked)
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: compact ? 92 : 236
            Layout.fillHeight: true
            color: theme.sidebar

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: compact ? 12 : 18
                spacing: 14

                Text {
                    Layout.fillWidth: true
                    text: compact ? "LA" : "LuckasApp"
                    color: theme.text
                    font.pixelSize: compact ? 24 : 28
                    font.bold: true
                    horizontalAlignment: compact ? Text.AlignHCenter : Text.AlignLeft
                    elide: Text.ElideRight
                }

                Rectangle {
                    Layout.fillWidth: true
                    height: compact ? 54 : 72
                    radius: 18
                    color: appBridge.connectionStatus === "Connected" ? "#143527" : "#231f28"
                    border.color: appBridge.connectionStatus === "Connected" ? "#2d6a52" : "#3a303c"
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 2
                        Text {
                            Layout.fillWidth: true
                            text: appBridge.connectionStatus
                            color: theme.text
                            font.pixelSize: 13
                            font.bold: true
                            horizontalAlignment: compact ? Text.AlignHCenter : Text.AlignLeft
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: compact ? appBridge.connectionMode : appBridge.currentServer
                            color: theme.muted
                            font.pixelSize: 11
                            horizontalAlignment: compact ? Text.AlignHCenter : Text.AlignLeft
                            elide: Text.ElideRight
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Repeater {
                        model: navItems
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            height: 46
                            radius: 15
                            color: currentPage === modelData ? theme.panel2 : "transparent"
                            border.color: currentPage === modelData ? theme.line : "transparent"
                            Text {
                                anchors.centerIn: parent
                                width: parent.width - 14
                                text: compact ? modelData.substring(0, 2).toUpperCase() : modelData
                                color: currentPage === modelData ? theme.text : theme.muted
                                font.pixelSize: compact ? 12 : 14
                                font.bold: currentPage === modelData
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: currentPage = modelData
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Text {
                    Layout.fillWidth: true
                    text: toast
                    color: theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 82
                color: theme.bg

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 22
                    anchors.rightMargin: 22
                    spacing: 12

                    Text {
                        text: currentPage
                        color: theme.text
                        font.pixelSize: narrow ? 22 : 28
                        font.bold: true
                        Layout.preferredWidth: narrow ? 150 : 230
                        elide: Text.ElideRight
                    }

                    TextField {
                        Layout.fillWidth: true
                        Layout.maximumWidth: compact ? 260 : 460
                        height: 42
                        text: searchText
                        placeholderText: "Search healthy nodes"
                        color: theme.text
                        placeholderTextColor: theme.muted
                        font.pixelSize: 13
                        onTextChanged: searchText = text
                        background: Rectangle {
                            radius: 15
                            color: theme.panel
                            border.color: theme.line
                        }
                    }

                    AppButton {
                        text: "SCAN"
                        fill: theme.green
                        ink: "#07120d"
                        Layout.preferredWidth: 84
                        onClicked: appBridge.scanUpdates()
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: (appBridge.validationRunning || (appBridge.busy && appBridge.progressTitle.length > 0)) ? 94 : 0
                visible: height > 0
                color: theme.bg
                clip: true

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.leftMargin: 22
                    anchors.rightMargin: 22
                    height: 78
                    radius: 20
                    color: theme.panel
                    border.color: theme.line

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: appBridge.progressTitle || "Working"
                                color: theme.text
                                font.pixelSize: 14
                                font.bold: true
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            Text {
                                text: appBridge.progressDone + " / " + appBridge.progressTotal
                                color: theme.muted
                                font.pixelSize: 12
                                visible: appBridge.progressTotal > 0
                            }
                        }
                        ProgressBar {
                            Layout.fillWidth: true
                            from: 0
                            to: 100
                            value: appBridge.progressValue
                            background: Rectangle { radius: 8; color: theme.panel2 }
                            contentItem: Item {
                                implicitHeight: 10
                                Rectangle {
                                    width: parent.width * appBridge.progressValue / 100
                                    height: parent.height
                                    radius: 8
                                    color: theme.green
                                }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: appBridge.progressDetail
                            color: theme.muted
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            ScrollView {
                id: pageScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth

                ColumnLayout {
                    width: Math.max(320, pageScroll.availableWidth - 44)
                    x: 22
                    spacing: 18

                    Item { Layout.preferredHeight: 2 }

                    ColumnLayout {
                        visible: currentPage === "Dashboard"
                        Layout.fillWidth: true
                        spacing: 18

                        GridLayout {
                            Layout.fillWidth: true
                            columns: narrow ? 2 : 4
                            columnSpacing: 14
                            rowSpacing: 14
                            StatCard { title: "Connection Status"; value: appBridge.connectionStatus; accent: appBridge.connectionStatus === "Connected" ? theme.green : theme.red }
                            StatCard { title: "Current Node"; value: appBridge.currentServer; accent: theme.blue }
                            StatCard { title: "Latency"; value: bestLatency(); accent: theme.amber }
                            StatCard { title: "Healthy Nodes"; value: String(configs.length || 0); accent: theme.green }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: narrow ? 610 : 386
                            radius: 24
                            color: theme.panel
                            border.color: theme.line

                            GridLayout {
                                anchors.fill: parent
                                anchors.margins: narrow ? 18 : 24
                                columns: narrow ? 1 : 2
                                columnSpacing: 28
                                rowSpacing: 18

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.alignment: Qt.AlignVCenter
                                    spacing: 18

                                    Rectangle {
                                        Layout.alignment: Qt.AlignHCenter
                                        width: narrow ? 206 : 244
                                        height: width
                                        radius: width / 2
                                        color: appBridge.connectionStatus === "Connected" ? "#143527" : "#182335"
                                        border.width: 2
                                        border.color: appBridge.connectionStatus === "Connected" ? theme.green : theme.blue
                                        scale: quickMouse.pressed ? 0.98 : (quickMouse.containsMouse ? 1.025 : 1)
                                        Behavior on scale { NumberAnimation { duration: 120 } }

                                        ColumnLayout {
                                            anchors.centerIn: parent
                                            width: parent.width - 46
                                            spacing: 8
                                            Text {
                                                Layout.fillWidth: true
                                                text: quickActionText()
                                                color: theme.text
                                                font.pixelSize: narrow ? 24 : 28
                                                font.bold: true
                                                horizontalAlignment: Text.AlignHCenter
                                                wrapMode: Text.WordWrap
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                text: appBridge.connectionStatus === "Connected" ? appBridge.currentServer : (bestNode().name || "Best healthy node")
                                                color: theme.muted
                                                font.pixelSize: 12
                                                horizontalAlignment: Text.AlignHCenter
                                                elide: Text.ElideRight
                                            }
                                        }

                                        MouseArea {
                                            id: quickMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: quickAction()
                                        }
                                    }

                                    RowLayout {
                                        Layout.alignment: Qt.AlignHCenter
                                        spacing: 10
                                        AppButton { text: "Refresh"; Layout.preferredWidth: 110; onClicked: appBridge.scanUpdates() }
                                        AppButton { text: "Validate"; Layout.preferredWidth: 110; onClicked: appBridge.startValidation() }
                                    }
                                }

                                SectionPanel {
                                    title: "Network Statistics"
                                    themePanel: theme.panel2
                                    themeText: theme.text
                                    themeMuted: theme.muted
                                    content: Component {
                                        ColumnLayout {
                                            spacing: 12
                                            InfoLine { label: "Upload Speed"; value: traffic.uploadSpeedText || "0 B/s" }
                                            InfoLine { label: "Download Speed"; value: traffic.downloadSpeedText || "0 B/s" }
                                            InfoLine { label: "Session Duration"; value: traffic.durationText || "00:00" }
                                            InfoLine { label: "Session Traffic"; value: traffic.sessionTotalText || "0 B" }
                                            InfoLine { label: "Backend Sync"; value: service.status || "Stopped" }
                                            InfoLine { label: "Last Sync"; value: service.last_sync || sync.updated || "Never" }
                                        }
                                    }
                                }
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: narrow ? 1 : 2
                            columnSpacing: 14
                            rowSpacing: 14

                            SectionPanel {
                                title: "Proxy Mode"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    ColumnLayout {
                                        spacing: 12
                                        InfoLine { label: "Status"; value: appBridge.proxyStatus === "enabled" ? "Active" : "Inactive" }
                                        InfoLine { label: "SOCKS Address"; value: "127.0.0.1" }
                                        InfoLine { label: "SOCKS Port"; value: String(settings.socks_port || 10808) }
                                        InfoLine { label: "HTTP Address"; value: "127.0.0.1" }
                                        InfoLine { label: "HTTP Port"; value: String(settings.http_port || 10809) }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            AppButton { text: "Enable Proxy Mode"; Layout.fillWidth: true; onClicked: appBridge.enableProxy() }
                                            AppButton { text: "Disable"; Layout.fillWidth: true; fill: theme.red; onClicked: appBridge.disableProxy() }
                                        }
                                    }
                                }
                            }

                            SectionPanel {
                                title: "TUN Mode"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    ColumnLayout {
                                        spacing: 12
                                        InfoLine { label: "TUN Status"; value: appBridge.vpnStatus }
                                        InfoLine { label: "DNS Status"; value: diagnostics.dns_status || "Unknown" }
                                        InfoLine { label: "Route Status"; value: diagnostics.route_status || "Unknown" }
                                        Text {
                                            Layout.fillWidth: true
                                            text: "TUN mode requires administrator privileges, a supported TUN driver, DNS routing, and route recovery."
                                            color: theme.muted
                                            font.pixelSize: 12
                                            wrapMode: Text.WordWrap
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            AppButton { text: "Enable TUN"; Layout.fillWidth: true; onClicked: appBridge.enableVpn() }
                                            AppButton { text: "Disable"; Layout.fillWidth: true; fill: theme.red; onClicked: appBridge.disableVpn() }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: currentPage === "Nodes"
                        Layout.fillWidth: true
                        spacing: 16

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: filtered(configs).length + " healthy nodes"
                                color: theme.muted
                                font.pixelSize: 13
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            AppButton { text: "SCAN"; Layout.preferredWidth: 92; onClicked: appBridge.scanUpdates() }
                            AppButton { text: "Validate"; Layout.preferredWidth: 110; onClicked: appBridge.startValidation() }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: root.width < 820 ? 1 : (root.width < 1260 ? 2 : 3)
                            columnSpacing: 14
                            rowSpacing: 14
                            Repeater {
                                model: filtered(configs)
                                delegate: ConfigCard {
                                    Layout.fillWidth: true
                                    item: modelData
                                    onConnectClicked: appBridge.connectConfig(modelData.id)
                                    onCopyClicked: appBridge.copyConfig(modelData.id)
                                    onFavoriteClicked: appBridge.toggleFavorite(modelData.id)
                                    onDetailsClicked: appBridge.showDetails(modelData.id)
                                }
                            }
                        }

                        SectionPanel {
                            visible: filtered(configs).length === 0
                            title: "No Healthy Nodes"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    Text {
                                        Layout.fillWidth: true
                                        text: "The app loads cache immediately. Use SCAN and Validate while the background service keeps checking nodes."
                                        color: theme.muted
                                        font.pixelSize: 13
                                        wrapMode: Text.WordWrap
                                    }
                                    AppButton { text: "SCAN"; Layout.preferredWidth: 140; fill: theme.green; ink: "#07120d"; onClicked: appBridge.scanUpdates() }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: currentPage === "Quick Connect"
                        Layout.fillWidth: true
                        spacing: 16

                        GridLayout {
                            Layout.fillWidth: true
                            columns: narrow ? 1 : 2
                            columnSpacing: 18
                            rowSpacing: 18

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 430
                                radius: 24
                                color: theme.panel
                                border.color: theme.line
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 24
                                    spacing: 18
                                    Rectangle {
                                        Layout.alignment: Qt.AlignHCenter
                                        width: 250
                                        height: 250
                                        radius: 125
                                        color: appBridge.connectionStatus === "Connected" ? "#143527" : "#182335"
                                        border.width: 2
                                        border.color: appBridge.connectionStatus === "Connected" ? theme.green : theme.blue
                                        Text {
                                            anchors.centerIn: parent
                                            width: parent.width - 44
                                            text: quickActionText()
                                            color: theme.text
                                            font.pixelSize: 28
                                            font.bold: true
                                            horizontalAlignment: Text.AlignHCenter
                                            wrapMode: Text.WordWrap
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: quickAction()
                                        }
                                    }
                                    InfoLine { label: "Best Node"; value: bestNode().name || "None" }
                                    InfoLine { label: "Protocol"; value: (bestNode().protocol || "").toUpperCase() }
                                    InfoLine { label: "Latency"; value: bestLatency() }
                                    InfoLine { label: "Health Score"; value: bestNode().score ? Math.round(bestNode().score) + " / 100" : "--" }
                                }
                            }

                            SectionPanel {
                                title: "Smart Ranking"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    ColumnLayout {
                                        spacing: 12
                                        InfoLine { label: "Best Latency"; value: bestLatency() }
                                        InfoLine { label: "Best Stability"; value: bestNode().quality || "--" }
                                        InfoLine { label: "Recent Validation"; value: bestNode().last_check_at || "Never" }
                                        InfoLine { label: "Success Rate"; value: bestNode().success_count ? String(bestNode().success_count) + " passed" : "--" }
                                        AppButton {
                                            text: "Connect Best Node"
                                            fill: theme.green
                                            ink: "#07120d"
                                            Layout.fillWidth: true
                                            onClicked: appBridge.smartConnect()
                                        }
                                        AppButton {
                                            text: "Disconnect"
                                            fill: theme.red
                                            Layout.fillWidth: true
                                            onClicked: appBridge.disconnect()
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: currentPage === "Statistics"
                        Layout.fillWidth: true
                        spacing: 16

                        GridLayout {
                            Layout.fillWidth: true
                            columns: narrow ? 2 : 4
                            columnSpacing: 14
                            rowSpacing: 14
                            StatCard { title: "Upload"; value: traffic.uploadSpeedText || "0 B/s"; accent: theme.green }
                            StatCard { title: "Download"; value: traffic.downloadSpeedText || "0 B/s"; accent: theme.blue }
                            StatCard { title: "Session"; value: traffic.durationText || "00:00"; accent: theme.amber }
                            StatCard { title: "Monthly Usage"; value: traffic.monthlyUsageText || "0 B"; accent: theme.red }
                        }

                        SectionPanel {
                            title: "Live Speed"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                SpeedChart {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 240
                                    points: traffic.speedPoints || []
                                }
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: narrow ? 1 : 2
                            columnSpacing: 14
                            rowSpacing: 14
                            SectionPanel {
                                title: "Daily Usage"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    UsageBars { Layout.fillWidth: true; Layout.preferredHeight: 160; items: traffic.daily || []; barColor: theme.green }
                                }
                            }
                            SectionPanel {
                                title: "Monthly Usage"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    UsageBars { Layout.fillWidth: true; Layout.preferredHeight: 160; items: traffic.monthly || []; barColor: theme.blue }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: currentPage === "Settings"
                        Layout.fillWidth: true
                        spacing: 16

                        GridLayout {
                            Layout.fillWidth: true
                            columns: narrow ? 1 : 2
                            columnSpacing: 14
                            rowSpacing: 14

                            SectionPanel {
                                title: "General"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    ColumnLayout {
                                        spacing: 12
                                        InfoLine { label: "Language"; value: settings.language || "English" }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            AppButton { text: "Dark"; Layout.fillWidth: true; fill: (settings.theme || "dark") === "dark" ? theme.green : theme.panel2; ink: (settings.theme || "dark") === "dark" ? "#07120d" : theme.text; onClicked: setTheme("dark") }
                                            AppButton { text: "Light"; Layout.fillWidth: true; fill: settings.theme === "light" ? theme.green : theme.panel2; ink: settings.theme === "light" ? "#07120d" : theme.text; onClicked: setTheme("light") }
                                        }
                                        ToggleLine { label: "Auto Start"; settingKey: "auto_start"; currentValue: !!settings.auto_start }
                                        ToggleLine { label: "Auto Connect"; settingKey: "auto_connect"; currentValue: !!settings.auto_connect }
                                    }
                                }
                            }

                            SectionPanel {
                                title: "Synchronization"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    ColumnLayout {
                                        spacing: 12
                                        ToggleLine { label: "Auto Sync"; settingKey: "auto_sync"; currentValue: settings.auto_sync === undefined ? true : settings.auto_sync }
                                        ToggleLine { label: "Background Service"; settingKey: "service_enabled"; currentValue: settings.service_enabled === undefined ? true : settings.service_enabled }
                                        InfoLine { label: "Sync Every"; value: String(settings.sync_interval || 5) + " minutes" }
                                        Slider { Layout.fillWidth: true; from: 1; to: 60; stepSize: 1; value: settings.sync_interval || 5; onMoved: appBridge.setSetting("sync_interval", Math.round(value)) }
                                        TextField {
                                            Layout.fillWidth: true
                                            text: settings.github_distribution_base_url || ""
                                            placeholderText: "GitHub distribution URL"
                                            color: theme.text
                                            placeholderTextColor: theme.muted
                                            onEditingFinished: appBridge.setSetting("github_distribution_base_url", text)
                                            background: Rectangle { radius: 14; color: theme.panel2; border.color: theme.line }
                                        }
                                        AppButton { text: "Manual Sync"; Layout.fillWidth: true; onClicked: appBridge.scanUpdates() }
                                    }
                                }
                            }

                            SectionPanel {
                                title: "Performance"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    ColumnLayout {
                                        spacing: 12
                                        InfoLine { label: "Concurrent Workers"; value: String(settings.validation_workers || 4) }
                                        Slider { Layout.fillWidth: true; from: 1; to: 32; stepSize: 1; value: settings.validation_workers || 4; onMoved: appBridge.setSetting("validation_workers", Math.round(value)) }
                                        InfoLine { label: "Service Batch"; value: String(settings.service_health_batch || 24) }
                                        Slider { Layout.fillWidth: true; from: 4; to: 128; stepSize: 4; value: settings.service_health_batch || 24; onMoved: appBridge.setSetting("service_health_batch", Math.round(value)) }
                                        InfoLine { label: "Cache Size"; value: String(settings.cache_size_mb || 512) + " MB" }
                                    }
                                }
                            }

                            SectionPanel {
                                title: "Windows Service"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    ColumnLayout {
                                        spacing: 12
                                        InfoLine { label: "Service Status"; value: service.status || "Stopped" }
                                        InfoLine { label: "Last Sync"; value: service.last_sync || "Never" }
                                        InfoLine { label: "Last Health"; value: service.last_health_check || "Never" }
                                        InfoLine { label: "Last Error"; value: service.last_error || "" }
                                        GridLayout {
                                            Layout.fillWidth: true
                                            columns: 2
                                            columnSpacing: 8
                                            rowSpacing: 8
                                            AppButton { text: "Install"; Layout.fillWidth: true; onClicked: appBridge.serviceControl("install") }
                                            AppButton { text: "Start"; Layout.fillWidth: true; onClicked: appBridge.serviceControl("start") }
                                            AppButton { text: "Stop"; Layout.fillWidth: true; fill: theme.red; onClicked: appBridge.serviceControl("stop") }
                                            AppButton { text: "Run Once"; Layout.fillWidth: true; onClicked: appBridge.serviceControl("run-once") }
                                        }
                                    }
                                }
                            }

                            SectionPanel {
                                title: "Diagnostics"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    ColumnLayout {
                                        spacing: 12
                                        InfoLine { label: "Core Status"; value: diagnostics.core_running ? "Running" : "Stopped" }
                                        InfoLine { label: "Service Status"; value: diagnostics.service_status || "Stopped" }
                                        InfoLine { label: "DNS Status"; value: diagnostics.dns_status || "Unknown" }
                                        InfoLine { label: "Routing Status"; value: diagnostics.route_status || "Unknown" }
                                        InfoLine { label: "TLS Status"; value: diagnostics.tls_status || "Unknown" }
                                        InfoLine { label: "Last Error"; value: diagnostics.last_error || diagnostics.service_last_error || "" }
                                        AppButton { text: "Restart Core"; Layout.fillWidth: true; onClicked: appBridge.restartCore() }
                                    }
                                }
                            }

                            SectionPanel {
                                title: "Advanced"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    ColumnLayout {
                                        spacing: 12
                                        ToggleLine { label: "SOCKS Proxy"; settingKey: "enable_socks"; currentValue: settings.enable_socks === undefined ? true : settings.enable_socks }
                                        ToggleLine { label: "HTTP Proxy"; settingKey: "enable_http"; currentValue: settings.enable_http === undefined ? true : settings.enable_http }
                                        ToggleLine { label: "TUN"; settingKey: "enable_tun"; currentValue: !!settings.enable_tun }
                                        ToggleLine { label: "Kill Switch"; settingKey: "kill_switch"; currentValue: !!settings.kill_switch }
                                        ToggleLine { label: "DNS Leak Protection"; settingKey: "dns_leak_protection"; currentValue: settings.dns_leak_protection === undefined ? true : settings.dns_leak_protection }
                                    }
                                }
                            }
                        }
                    }

                    Item { Layout.preferredHeight: 24 }
                }
            }
        }
    }
}
