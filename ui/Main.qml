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
    property string currentPage: "Home"
    property string settingsTab: "General"
    property string toast: "Ready"
    property string searchText: ""
    property var configs: []
    property var favorites: []
    property var stats: ({})
    property var traffic: ({ speedPoints: [], daily: [], weekly: [], monthly: [] })
    property var sources: []
    property var repositories: []
    property var history: []
    property var settings: ({})
    property var sync: ({})
    property var update: ({})
    property var navItems: ["Home", "Scan", "Servers", "Favorites", "Statistics", "History", "Settings"]
    property var settingTabs: ["General", "Synchronization", "Performance", "Notifications", "Advanced"]

    function reloadAll() {
        configs = appBridge.configList()
        favorites = appBridge.favoriteList()
        stats = appBridge.stats()
        traffic = appBridge.trafficStats()
        sources = appBridge.sourceList()
        repositories = appBridge.repositoryList()
        history = appBridge.historyList()
        settings = appBridge.appSettings()
        sync = appBridge.syncStatus()
        update = appBridge.updateStatus()
        applyTheme(settings.theme || "dark")
    }

    function refreshLive() {
        stats = appBridge.stats()
        traffic = appBridge.trafficStats()
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
                || (item.status || "").toLowerCase().indexOf(text) >= 0
        })
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

    function connectionLabel() {
        if (appBridge.connectionMode === "disconnected")
            return "Disconnected"
        return "Connected"
    }

    function quickActionText() {
        if (appBridge.busy && appBridge.connectionMode === "disconnected")
            return "Connecting"
        if (appBridge.connectionMode !== "disconnected")
            return "Disconnect"
        return "Quick Connect"
    }

    function quickAction() {
        if (appBridge.connectionMode !== "disconnected")
            appBridge.disconnect()
        else
            appBridge.smartConnect()
    }

    function lastUpdateText() {
        if (sync.updated)
            return sync.updated
        if (update.remote_version)
            return update.remote_version
        return "Not synced"
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
        function onSourcesChanged() { sources = appBridge.sourceList(); repositories = appBridge.repositoryList() }
        function onStatsChanged() { stats = appBridge.stats() }
        function onTrafficChanged() { traffic = appBridge.trafficStats() }
        function onSettingsChanged() { settings = appBridge.appSettings(); applyTheme(settings.theme || "dark") }
        function onSyncChanged() { sync = appBridge.syncStatus() }
        function onUpdateChanged() { update = appBridge.updateStatus() }
        function onCurrentServerChanged() { stats = appBridge.stats() }
        function onConnectionModeChanged() { stats = appBridge.stats() }
        function onNotification(message) { toast = message; history = appBridge.historyList() }
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

    component Badge: Rectangle {
        id: badge
        property string label: ""
        property color fill: theme.panel2
        implicitWidth: Math.max(86, labelText.implicitWidth + 28)
        height: 32
        radius: 16
        color: fill
        border.color: theme.line
        Text {
            id: labelText
            anchors.centerIn: parent
            text: badge.label
            color: theme.text
            font.pixelSize: 12
            font.bold: true
            elide: Text.ElideRight
            width: parent.width - 14
            horizontalAlignment: Text.AlignHCenter
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
            Layout.preferredWidth: 128
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
            Layout.preferredWidth: compact ? 88 : 232
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
                    height: compact ? 54 : 68
                    radius: 18
                    color: appBridge.connectionMode === "disconnected" ? "#231f28" : "#143527"
                    border.color: appBridge.connectionMode === "disconnected" ? "#3a303c" : "#2d6a52"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 2
                        Text {
                            Layout.fillWidth: true
                            text: connectionLabel()
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
                        Layout.preferredWidth: narrow ? 128 : 190
                        elide: Text.ElideRight
                    }

                    TextField {
                        id: searchBox
                        Layout.fillWidth: true
                        Layout.maximumWidth: compact ? 260 : 460
                        height: 42
                        text: searchText
                        placeholderText: "Search"
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

                    Badge {
                        label: (sync.status || "idle")
                        fill: sync.status === "complete" ? "#163728" : theme.panel
                        visible: !narrow
                    }

                    AppButton {
                        text: "Sync"
                        fill: theme.panel
                        Layout.preferredWidth: 76
                        onClicked: appBridge.scanUpdates()
                    }

                    AppButton {
                        text: "Settings"
                        fill: theme.panel
                        Layout.preferredWidth: narrow ? 42 : 96
                        onClicked: currentPage = "Settings"
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
                        visible: currentPage === "Home"
                        Layout.fillWidth: true
                        spacing: 18

                        GridLayout {
                            Layout.fillWidth: true
                            columns: narrow ? 2 : 4
                            columnSpacing: 14
                            rowSpacing: 14

                            StatCard { title: "Total Records"; value: String(stats.total || 0); accent: theme.blue }
                            StatCard { title: "New Records"; value: String(sync.new_records || 0); accent: theme.green }
                            StatCard { title: "Last Sync"; value: lastUpdateText(); accent: theme.amber }
                            StatCard { title: "Active Tests"; value: appBridge.validationRunning ? String(stats.testing || 0) : "0"; accent: appBridge.validationRunning ? theme.green : theme.red }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: narrow ? 590 : 374
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
                                        width: narrow ? 206 : 238
                                        height: width
                                        radius: width / 2
                                        color: appBridge.connectionMode === "disconnected" ? "#182335" : "#143527"
                                        border.width: 2
                                        border.color: appBridge.connectionMode === "disconnected" ? theme.blue : theme.green
                                        scale: quickMouse.pressed ? 0.98 : (quickMouse.containsMouse ? 1.025 : 1)
                                        Behavior on scale { NumberAnimation { duration: 120 } }

                                        ColumnLayout {
                                            anchors.centerIn: parent
                                            width: parent.width - 42
                                            spacing: 8
                                            Text {
                                                Layout.fillWidth: true
                                                text: quickActionText()
                                                color: theme.text
                                                font.pixelSize: narrow ? 23 : 27
                                                font.bold: true
                                                horizontalAlignment: Text.AlignHCenter
                                                wrapMode: Text.WordWrap
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                text: appBridge.connectionMode === "disconnected" ? "Best ready node" : appBridge.currentServer
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
                                        AppButton {
                                            text: "SCAN"
                                            fill: theme.green
                                            ink: "#07120d"
                                            Layout.preferredWidth: 136
                                            onClicked: appBridge.scanUpdates()
                                        }
                                        AppButton {
                                            text: "Refresh"
                                            fill: theme.panel2
                                            Layout.preferredWidth: 112
                                            onClicked: appBridge.refreshConfigs()
                                        }
                                    }
                                }

                                SectionPanel {
                                    title: "Connection Panel"
                                    themePanel: theme.panel2
                                    themeText: theme.text
                                    themeMuted: theme.muted
                                    content: Component {
                                        ColumnLayout {
                                            spacing: 12
                                            InfoLine { label: "Current Server"; value: appBridge.currentServer }
                                            InfoLine { label: "Mode"; value: appBridge.connectionMode }
                                            InfoLine { label: "Upload"; value: traffic.uploadSpeedText || "0 B/s" }
                                            InfoLine { label: "Download"; value: traffic.downloadSpeedText || "0 B/s" }
                                            InfoLine { label: "Duration"; value: traffic.durationText || "00:00" }
                                            InfoLine { label: "Session Traffic"; value: traffic.sessionTotalText || "0 B" }
                                            RowLayout {
                                                Layout.fillWidth: true
                                                spacing: 10
                                                AppButton { text: "Proxy"; Layout.fillWidth: true; onClicked: appBridge.enableProxy() }
                                                AppButton { text: "Disconnect"; Layout.fillWidth: true; fill: theme.red; onClicked: appBridge.disconnect() }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: currentPage === "Servers"
                        Layout.fillWidth: true
                        spacing: 16

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: filtered(configs).length + " servers"
                                color: theme.muted
                                font.pixelSize: 13
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            AppButton { text: "Validate"; Layout.preferredWidth: 110; onClicked: appBridge.startValidation() }
                            AppButton { text: "Refresh"; Layout.preferredWidth: 100; onClicked: appBridge.refreshConfigs() }
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
                                    onDisconnectClicked: appBridge.disconnect()
                                    onTestClicked: appBridge.testConfig(modelData.id)
                                    onCopyClicked: appBridge.copyConfig(modelData.id)
                                    onFavoriteClicked: appBridge.toggleFavorite(modelData.id)
                                    onExportClicked: appBridge.exportConfig(modelData.id)
                                    onDetailsClicked: appBridge.showDetails(modelData.id)
                                    onDeleteClicked: appBridge.deleteConfig(modelData.id)
                                }
                            }
                        }

                        SectionPanel {
                            visible: filtered(configs).length === 0
                            title: "No Servers"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    Text {
                                        Layout.fillWidth: true
                                        text: "Use Scan or Refresh to import servers."
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
                        visible: currentPage === "Scan"
                        Layout.fillWidth: true
                        spacing: 16

                        SectionPanel {
                            title: "Scan"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 14
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: narrow ? 1 : 3
                                        columnSpacing: 10
                                        rowSpacing: 10
                                        AppButton { text: "SCAN"; fill: theme.green; ink: "#07120d"; Layout.fillWidth: true; onClicked: appBridge.scanUpdates() }
                                        AppButton { text: "Refresh"; Layout.fillWidth: true; onClicked: appBridge.refreshConfigs() }
                                        AppButton { text: appBridge.validationRunning ? "Stop Test" : "Validate"; Layout.fillWidth: true; onClicked: appBridge.validationRunning ? appBridge.stopValidation() : appBridge.startValidation() }
                                    }
                                    InfoLine { label: "Sync Status"; value: sync.status || "idle" }
                                    InfoLine { label: "Records"; value: String(sync.records || 0) }
                                    InfoLine { label: "New Records"; value: String(sync.new_records || 0) }
                                    InfoLine { label: "Repositories"; value: String(repositories.length || 0) }
                                }
                            }
                        }

                        SectionPanel {
                            title: "GitHub"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    InfoLine { label: "Owner"; value: settings.github_owner || "luckasgh9170" }
                                    InfoLine { label: "Repository"; value: settings.github_repository || "luckasapp" }
                                    InfoLine { label: "Branch"; value: settings.github_branch || "main" }
                                    TextField {
                                        Layout.fillWidth: true
                                        text: settings.github_distribution_base_url || ""
                                        placeholderText: "GitHub distribution base URL"
                                        color: theme.text
                                        placeholderTextColor: theme.muted
                                        onEditingFinished: appBridge.setSetting("github_distribution_base_url", text)
                                        background: Rectangle { radius: 14; color: theme.panel2; border.color: theme.line }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        AppButton { text: "Discover"; Layout.fillWidth: true; onClicked: appBridge.discoverSources() }
                                        AppButton { text: "Build"; Layout.fillWidth: true; onClicked: appBridge.buildDistribution() }
                                        AppButton { text: "Publish"; Layout.fillWidth: true; onClicked: appBridge.publishDistribution() }
                                    }
                                }
                            }
                        }

                        SectionPanel {
                            title: "Updates"
                            themePanel: update.update_available ? "#172d24" : theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    InfoLine { label: "Status"; value: update.message || update.status || "idle" }
                                    InfoLine { label: "Local Version"; value: update.local_version || "0.0.0" }
                                    InfoLine { label: "Remote Version"; value: update.remote_version || "unknown" }
                                    Text {
                                        Layout.fillWidth: true
                                        text: update.release_notes || "No release notes."
                                        color: theme.muted
                                        font.pixelSize: 13
                                        wrapMode: Text.WordWrap
                                        maximumLineCount: 3
                                    }
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: narrow ? 1 : 4
                                        columnSpacing: 10
                                        rowSpacing: 10
                                        AppButton { text: "Check"; Layout.fillWidth: true; onClicked: appBridge.checkForUpdates() }
                                        AppButton { text: "Update Now"; Layout.fillWidth: true; fill: theme.green; ink: "#07120d"; enabled: update.update_available; onClicked: appBridge.updateNow() }
                                        AppButton { text: "Later"; Layout.fillWidth: true; enabled: update.update_available; onClicked: appBridge.updateLater() }
                                        AppButton { text: "Skip Version"; Layout.fillWidth: true; enabled: update.update_available; onClicked: appBridge.skipUpdateVersion() }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: currentPage === "Favorites"
                        Layout.fillWidth: true
                        spacing: 16

                        GridLayout {
                            Layout.fillWidth: true
                            columns: root.width < 820 ? 1 : (root.width < 1260 ? 2 : 3)
                            columnSpacing: 14
                            rowSpacing: 14

                            Repeater {
                                model: filtered(favorites)
                                delegate: ConfigCard {
                                    Layout.fillWidth: true
                                    item: modelData
                                    onConnectClicked: appBridge.connectConfig(modelData.id)
                                    onDisconnectClicked: appBridge.disconnect()
                                    onTestClicked: appBridge.testConfig(modelData.id)
                                    onCopyClicked: appBridge.copyConfig(modelData.id)
                                    onFavoriteClicked: appBridge.toggleFavorite(modelData.id)
                                    onExportClicked: appBridge.exportConfig(modelData.id)
                                    onDetailsClicked: appBridge.showDetails(modelData.id)
                                    onDeleteClicked: appBridge.deleteConfig(modelData.id)
                                }
                            }
                        }

                        SectionPanel {
                            visible: filtered(favorites).length === 0
                            title: "No Favorites"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                Text {
                                    text: "Favorite a server to keep it here."
                                    color: theme.muted
                                    font.pixelSize: 13
                                    wrapMode: Text.WordWrap
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
                                ColumnLayout {
                                    spacing: 14
                                    SpeedChart {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 220
                                        points: traffic.speedPoints || []
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        InfoLine { label: "Peak Upload"; value: traffic.peakUploadSpeedText || "0 B/s" }
                                        InfoLine { label: "Peak Download"; value: traffic.peakDownloadSpeedText || "0 B/s" }
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
                                title: "Daily Usage"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    UsageBars {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 160
                                        items: traffic.daily || []
                                        barColor: theme.green
                                    }
                                }
                            }

                            SectionPanel {
                                title: "Weekly Usage"
                                themePanel: theme.panel
                                themeText: theme.text
                                themeMuted: theme.muted
                                content: Component {
                                    UsageBars {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 160
                                        items: traffic.weekly || []
                                        barColor: theme.blue
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: currentPage === "History"
                        Layout.fillWidth: true
                        spacing: 16

                        GridLayout {
                            Layout.fillWidth: true
                            columns: narrow ? 2 : 4
                            columnSpacing: 14
                            rowSpacing: 14

                            StatCard { title: "Recent Activity"; value: String(history.length || 0); accent: theme.blue }
                            StatCard { title: "Last Sync"; value: lastUpdateText(); accent: theme.amber }
                            StatCard { title: "New Records"; value: String(sync.new_records || 0); accent: theme.green }
                            StatCard { title: "Current Server"; value: appBridge.currentServer; accent: appBridge.connectionMode === "disconnected" ? theme.red : theme.green }
                        }

                        SectionPanel {
                            title: "Recent Activity"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 10
                                    Repeater {
                                        model: history.slice(0, 30)
                                        delegate: Rectangle {
                                            Layout.fillWidth: true
                                            height: 54
                                            radius: 16
                                            color: theme.panel2
                                            border.color: theme.line
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.margins: 12
                                                spacing: 10
                                                Text {
                                                    text: modelData.event || "event"
                                                    color: theme.text
                                                    font.pixelSize: 13
                                                    font.bold: true
                                                    Layout.preferredWidth: 112
                                                    elide: Text.ElideRight
                                                }
                                                Text {
                                                    text: modelData.name || modelData.remote_version || modelData.mode || modelData.path || ""
                                                    color: theme.muted
                                                    font.pixelSize: 12
                                                    Layout.fillWidth: true
                                                    elide: Text.ElideRight
                                                }
                                                Text {
                                                    text: modelData.time || ""
                                                    color: theme.muted
                                                    font.pixelSize: 11
                                                    Layout.preferredWidth: narrow ? 0 : 160
                                                    visible: !narrow
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                    }
                                    Text {
                                        visible: history.length === 0
                                        Layout.fillWidth: true
                                        text: "No recent activity yet."
                                        color: theme.muted
                                        font.pixelSize: 13
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: currentPage === "Settings"
                        Layout.fillWidth: true
                        spacing: 16

                        ScrollView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 56
                            contentWidth: tabRow.implicitWidth
                            clip: true
                            RowLayout {
                                id: tabRow
                                spacing: 8
                                Repeater {
                                    model: settingTabs
                                    delegate: AppButton {
                                        text: modelData
                                        fill: settingsTab === modelData ? theme.green : theme.panel
                                        ink: settingsTab === modelData ? "#07120d" : theme.text
                                        Layout.preferredWidth: 120
                                        onClicked: settingsTab = modelData
                                    }
                                }
                            }
                        }

                        SectionPanel {
                            visible: settingsTab === "General"
                            title: "General"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    InfoLine { label: "Language"; value: settings.language || "English" }
                                    Text {
                                        Layout.fillWidth: true
                                        text: "Theme"
                                        color: theme.muted
                                        font.pixelSize: 12
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 10
                                        AppButton { text: "Dark"; Layout.preferredWidth: 110; fill: (settings.theme || "dark") === "dark" ? theme.green : theme.panel2; ink: (settings.theme || "dark") === "dark" ? "#07120d" : theme.text; onClicked: setTheme("dark") }
                                        AppButton { text: "Light"; Layout.preferredWidth: 110; fill: settings.theme === "light" ? theme.green : theme.panel2; ink: settings.theme === "light" ? "#07120d" : theme.text; onClicked: setTheme("light") }
                                        AppButton { text: "System"; Layout.preferredWidth: 110; onClicked: setTheme("system") }
                                    }
                                    ToggleLine { label: "Auto Start"; settingKey: "auto_start"; currentValue: !!settings.auto_start }
                                    ToggleLine { label: "Auto Connect"; settingKey: "auto_connect"; currentValue: !!settings.auto_connect }
                                    ToggleLine { label: "Smart Connect"; settingKey: "smart_connect"; currentValue: settings.smart_connect === undefined ? true : settings.smart_connect }
                                }
                            }
                        }

                        SectionPanel {
                            visible: settingsTab === "Synchronization"
                            title: "Synchronization"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    ToggleLine { label: "Auto Sync"; settingKey: "auto_sync"; currentValue: settings.auto_sync === undefined ? true : settings.auto_sync }
                                    InfoLine { label: "Sync Every"; value: String(settings.sync_interval || 5) + " minutes" }
                                    Slider {
                                        Layout.fillWidth: true
                                        from: 1
                                        to: 60
                                        stepSize: 1
                                        value: settings.sync_interval || 5
                                        onMoved: appBridge.setSetting("sync_interval", Math.round(value))
                                    }
                                    TextField {
                                        Layout.fillWidth: true
                                        text: settings.github_distribution_base_url || ""
                                        placeholderText: "GitHub dataset URL"
                                        color: theme.text
                                        placeholderTextColor: theme.muted
                                        onEditingFinished: appBridge.setSetting("github_distribution_base_url", text)
                                        background: Rectangle { radius: 14; color: theme.panel2; border.color: theme.line }
                                    }
                                    ToggleLine { label: "Auto Update"; settingKey: "auto_update"; currentValue: settings.auto_update === undefined ? true : settings.auto_update }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        AppButton { text: "Manual Sync"; Layout.fillWidth: true; onClicked: appBridge.scanUpdates() }
                                        AppButton { text: "Check App Update"; Layout.fillWidth: true; onClicked: appBridge.checkForUpdates() }
                                    }
                                }
                            }
                        }

                        SectionPanel {
                            visible: settingsTab === "Network"
                            title: "Network"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    TextField {
                                        Layout.fillWidth: true
                                        text: settings.dns_server || "1.1.1.1"
                                        placeholderText: "DNS Server"
                                        color: theme.text
                                        placeholderTextColor: theme.muted
                                        onEditingFinished: appBridge.setSetting("dns_server", text)
                                        background: Rectangle { radius: 14; color: theme.panel2; border.color: theme.line }
                                    }
                                    ToggleLine { label: "IPv6"; settingKey: "ipv6"; currentValue: settings.ipv6 === undefined ? true : settings.ipv6 }
                                    ToggleLine { label: "DNS Cache"; settingKey: "dns_cache"; currentValue: settings.dns_cache === undefined ? true : settings.dns_cache }
                                    ToggleLine { label: "SOCKS Proxy"; settingKey: "enable_socks"; currentValue: settings.enable_socks === undefined ? true : settings.enable_socks }
                                    ToggleLine { label: "HTTP Proxy"; settingKey: "enable_http"; currentValue: settings.enable_http === undefined ? true : settings.enable_http }
                                }
                            }
                        }

                        SectionPanel {
                            visible: settingsTab === "Notifications"
                            title: "Notifications"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    ToggleLine { label: "Sync Complete"; settingKey: "sync_complete_notifications"; currentValue: settings.sync_complete_notifications === undefined ? true : settings.sync_complete_notifications }
                                    ToggleLine { label: "New Records"; settingKey: "new_update_notifications"; currentValue: settings.new_update_notifications === undefined ? true : settings.new_update_notifications }
                                    ToggleLine { label: "Errors"; settingKey: "error_notifications"; currentValue: settings.error_notifications === undefined ? true : settings.error_notifications }
                                    ToggleLine { label: "Beta Channel"; settingKey: "beta_channel"; currentValue: !!settings.beta_channel }
                                }
                            }
                        }

                        SectionPanel {
                            visible: settingsTab === "Performance"
                            title: "Performance"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    InfoLine { label: "Workers"; value: String(settings.validation_workers || 4) }
                                    Slider {
                                        Layout.fillWidth: true
                                        from: 1
                                        to: 32
                                        stepSize: 1
                                        value: settings.validation_workers || 4
                                        onMoved: appBridge.setSetting("validation_workers", Math.round(value))
                                    }
                                    InfoLine { label: "Timeout"; value: String(settings.validation_timeout || 8) + " seconds" }
                                    Slider {
                                        Layout.fillWidth: true
                                        from: 2
                                        to: 30
                                        stepSize: 1
                                        value: settings.validation_timeout || 8
                                        onMoved: appBridge.setSetting("validation_timeout", Math.round(value))
                                    }
                                    ToggleLine { label: "Auto Recheck"; settingKey: "auto_recheck"; currentValue: !!settings.auto_recheck }
                                }
                            }
                        }

                        SectionPanel {
                            visible: settingsTab === "Advanced"
                            title: "Advanced"
                            themePanel: theme.panel
                            themeText: theme.text
                            themeMuted: theme.muted
                            content: Component {
                                ColumnLayout {
                                    spacing: 12
                                    ToggleLine { label: "TUN"; settingKey: "enable_tun"; currentValue: !!settings.enable_tun }
                                    ToggleLine { label: "Kill Switch"; settingKey: "kill_switch"; currentValue: !!settings.kill_switch }
                                    ToggleLine { label: "DNS Leak Protection"; settingKey: "dns_leak_protection"; currentValue: settings.dns_leak_protection === undefined ? true : settings.dns_leak_protection }
                                    ToggleLine { label: "Encrypted Storage"; settingKey: "encrypted_storage"; currentValue: !!settings.encrypted_storage }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        AppButton { text: "Restart Core"; Layout.fillWidth: true; onClicked: appBridge.restartCore() }
                                        AppButton { text: "Stop Core"; Layout.fillWidth: true; fill: theme.red; onClicked: appBridge.stopCore() }
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
