import QtQuick

Rectangle {
    id: surface
    property color surfaceColor: "#24242b"
    property color highlightColor: "#eeeaf0"
    property real surfaceAlpha: 0.80
    property real edgeAlpha: 0.055
    color: Qt.alpha(surfaceColor, surfaceAlpha)
    border.width: 1
    border.color: Qt.alpha(highlightColor, edgeAlpha)

    // A quiet surface highlight; content remains fully opaque and unfiltered.
    Rectangle {
        anchors.fill: parent
        radius: surface.radius
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0.025) }
            GradientStop { position: 0.45; color: "transparent" }
            GradientStop { position: 1; color: "transparent" }
        }
    }
}
