import QtQuick
Canvas {
    id: root
    property real value: 0
    property color strokeColor: "white"
    property color trackColor: "#444444"
    property real lineWidth: 7
    property real startAngle: -90
    property real sweepAngle: 360
    property real animatedValue: value
    Behavior on animatedValue { NumberAnimation { duration: 650; easing.type: Easing.OutCubic } }
    antialiasing: true
    onAnimatedValueChanged: requestPaint()
    onStrokeColorChanged: requestPaint()
    onTrackColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        let c = getContext("2d"); c.reset(); c.lineCap = "round"; c.lineWidth = lineWidth;
        const cx = width/2, cy = height/2, r = Math.min(width,height)/2-lineWidth;
        const a = startAngle*Math.PI/180, sweep = sweepAngle*Math.PI/180;
        c.strokeStyle = trackColor; c.beginPath(); c.arc(cx,cy,r,a,a+sweep); c.stroke();
        const v = Math.max(0,Math.min(1,animatedValue/100));
        if (v > 0) { c.strokeStyle = strokeColor; c.beginPath(); c.arc(cx,cy,r,a,a+sweep*v); c.stroke(); }
    }
}
