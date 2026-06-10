import QtQuick

Canvas {
    id: chart
    property var points: []
    property color uploadColor: "#53d6a2"
    property color downloadColor: "#78a8ff"
    property color gridColor: "#2a3140"

    onPointsChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        ctx.clearRect(0, 0, width, height)
        ctx.strokeStyle = gridColor
        ctx.lineWidth = 1
        for (var i = 1; i < 4; i++) {
            var y = height * i / 4
            ctx.beginPath()
            ctx.moveTo(0, y)
            ctx.lineTo(width, y)
            ctx.stroke()
        }
        if (!points || points.length < 2)
            return
        var maxValue = 1
        for (var j = 0; j < points.length; j++)
            maxValue = Math.max(maxValue, points[j].up || 0, points[j].down || 0)
        drawLine("down", downloadColor, maxValue)
        drawLine("up", uploadColor, maxValue)
    }

    function drawLine(key, color, maxValue) {
        var ctx = getContext("2d")
        ctx.strokeStyle = color
        ctx.lineWidth = 2
        ctx.beginPath()
        for (var i = 0; i < points.length; i++) {
            var x = points.length === 1 ? 0 : width * i / (points.length - 1)
            var y = height - ((points[i][key] || 0) / maxValue) * (height - 12) - 6
            if (i === 0)
                ctx.moveTo(x, y)
            else
                ctx.lineTo(x, y)
        }
        ctx.stroke()
    }
}
