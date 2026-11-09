import QtQuick
Text {
    property string name: "circle"
    property real size: 24
    text: name
    font.family: "Material Symbols Rounded"
    font.pixelSize: size
    font.weight: Font.Normal
    font.variableAxes: ({"FILL": 0, "wght": 400, "GRAD": 0, "opsz": 24})
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    renderType: Text.QtRendering
    color: "white"
}
