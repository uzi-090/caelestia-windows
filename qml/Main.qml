import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Shapes
import QtQuick.Effects
import "pages"

Window {
    id: window
    title: "Caelestia for Windows"
    width: controller.windowWidth
    height: controller.windowHeight
    x: controller.windowX
    y: controller.windowY
    visible: !controller.gameBlocked
    color: "transparent"
    flags: Qt.FramelessWindowHint | (controller.testing ? Qt.Window : Qt.Tool) | Qt.WindowStaysOnTopHint
    property int currentTab: 0
    property bool validationCapture: false
    property real slide: controller.opened ? 0 : 1
    readonly property var shellPalette: {
        const palette = Object.assign({}, wallpaper.data);
        palette.card = Qt.alpha(palette.card || "#24242b", 0.86);
        palette.cardAlt = Qt.alpha(palette.cardAlt || "#303039", 0.88);
        return palette;
    }
    readonly property real uiScale: controller.scaleFactor
    readonly property real deviceScale: Screen.devicePixelRatio
    readonly property var pages: [dash,media,performance,weather]
    property real bodyWidth: pages[currentTab].implicitWidth+32
    property real bodyHeight: pages[currentTab].implicitHeight+114
    readonly property real panelLeft: Math.round((x+(width-bodyWidth*uiScale)/2)*deviceScale)/deviceScale-x
    readonly property real panelTop: (-bodyHeight-5)*slide*uiScale
    readonly property real panelWidth: bodyWidth*uiScale
    readonly property real panelHeight: bodyHeight*uiScale
    property bool animationBusy:slideAnimation.running || widthAnimation.running || heightAnimation.running || pageAnimation.running
    function selectTab(n) { currentTab=Math.max(0,Math.min(3,n)) }
    Behavior on slide { enabled:!controller.gameBlocked;NumberAnimation{id:slideAnimation;duration:500;easing.type:Easing.BezierSpline;easing.bezierCurve:[0.38,1.21,0.22,1,1,1]} }
    Behavior on bodyWidth { NumberAnimation{id:widthAnimation;duration:500;easing.type:Easing.BezierSpline;easing.bezierCurve:[0.38,1.21,0.22,1,1,1]} }
    Behavior on bodyHeight { NumberAnimation{id:heightAnimation;duration:500;easing.type:Easing.BezierSpline;easing.bezierCurve:[0.38,1.21,0.22,1,1,1]} }
    Connections {target:controller;function onTabRequested(n){window.selectTab(n)}}
    Shortcut {enabled:!window.validationCapture;sequence:"Escape";onActivated:controller.hidePanel()}
    Shortcut {enabled:!window.validationCapture;sequence:"Ctrl+1";onActivated:window.selectTab(0)}
    Shortcut {enabled:!window.validationCapture;sequence:"Ctrl+2";onActivated:window.selectTab(1)}
    Shortcut {enabled:!window.validationCapture;sequence:"Ctrl+3";onActivated:window.selectTab(2)}
    Shortcut {enabled:!window.validationCapture;sequence:"Ctrl+4";onActivated:window.selectTab(3)}

    Item {
        id:panel
        enabled:!window.validationCapture
        x:window.panelLeft-24*window.uiScale;y:window.panelTop
        width:window.bodyWidth+48;height:window.bodyHeight
        scale:window.uiScale;transformOrigin:Item.TopLeft
        opacity:Math.min(1,Math.max(0,1-window.slide))
        visible:window.slide<1
        // Group only the entrance/exit fade; settled text stays in the native scene.
        layer.enabled:visible && opacity>0 && opacity<1
        layer.textureSize:Qt.size(Math.ceil(width*window.uiScale*window.deviceScale),Math.ceil(height*window.uiScale*window.deviceScale))
        layer.smooth:true
        Item {
            id:glassSurface
            width:panel.width;height:panel.height
            layer.enabled:true
            layer.textureSize:Qt.size(Math.ceil(width*window.uiScale*window.deviceScale),Math.ceil(height*window.uiScale*window.deviceScale))
            layer.smooth:true
            layer.effect:MultiEffect {maskEnabled:true;maskSource:panelMask;maskThresholdMin:0.5;maskSpreadAtMin:1}
            Shape {
                id:panelMask;anchors.fill:parent;visible:false;layer.enabled:true
                layer.textureSize:glassSurface.layer.textureSize
                layer.smooth:true
                preferredRendererType:Shape.CurveRenderer
                ShapePath {
                    fillColor:"white";strokeWidth:-1
                    PathSvg {path:"M0,0 H"+glassSurface.width+
                        " Q"+(glassSurface.width-24)+",0 "+(glassSurface.width-24)+",24"+
                        " V"+(glassSurface.height-26)+
                        " Q"+(glassSurface.width-24)+","+glassSurface.height+" "+(glassSurface.width-50)+","+glassSurface.height+
                        " H50 Q24,"+glassSurface.height+" 24,"+(glassSurface.height-26)+
                        " V24 Q24,0 0,0 Z"}
                }
            }
            Image {
                source:window.shellPalette.wallpaperUrl || ""
                x:-(window.x+panel.x)/window.uiScale
                y:-(window.y+panel.y)/window.uiScale
                width:controller.screenWidth/window.uiScale
                height:controller.screenHeight/window.uiScale
                fillMode:Image.Stretch;asynchronous:true;cache:true;smooth:true
            }
            Rectangle {anchors.fill:parent;color:Qt.alpha(window.shellPalette.background || "#15151a",0.82)}
        }
        Rectangle {x:40;y:86;width:parent.width-80;height:1;color:Qt.alpha(window.shellPalette.outline,0.32)}
        Item {
            id:tabs;x:40;y:15;width:parent.width-80;height:66
            Rectangle {
                x:tabs.width/4*window.currentTab+2;y:0;width:tabs.width/4-4;height:60;radius:10
                color:Qt.alpha(window.shellPalette.primary,0.10)
                Behavior on x {NumberAnimation{duration:500;easing.type:Easing.BezierSpline;easing.bezierCurve:[0.38,1.21,0.22,1,1,1]}}
                Behavior on width {NumberAnimation{duration:500;easing.type:Easing.BezierSpline;easing.bezierCurve:[0.38,1.21,0.22,1,1,1]}}
            }
            Repeater {
                model:[{name:"Dashboard",icon:"dashboard"},{name:"Media",icon:"queue_music"},{name:"Performance",icon:"speed"},{name:"Weather",icon:"cloud"}]
                delegate:Item {
                    required property int index
                    required property var modelData
                    x:tabs.width/4*index;width:tabs.width/4;height:66
                    Icon {x:(parent.width-width)/2;y:6;name:modelData.icon;size:20;color:window.currentTab===index ? window.shellPalette.primary:window.shellPalette.foreground}
                    Text {anchors.horizontalCenter:parent.horizontalCenter;y:35;text:modelData.name;font.family:"Rubik";font.pixelSize:16;renderType:Text.QtRendering;renderTypeQuality:Text.HighRenderTypeQuality;color:window.currentTab===index ? window.shellPalette.primary:window.shellPalette.foreground}
                    Rectangle {width:parent.width;height:60;radius:10;color:window.shellPalette.foreground;opacity:tabMouse.containsMouse ? 0.045:0;Behavior on opacity{NumberAnimation{duration:150}}}
                    MouseArea {id:tabMouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:window.selectTab(index)}
                }
            }
            Rectangle {
                x:tabs.width/4*(window.currentTab+0.5)-21;y:61;width:42;height:3;radius:2;color:window.shellPalette.primary
                Behavior on x {NumberAnimation{duration:500;easing.type:Easing.BezierSpline;easing.bezierCurve:[0.38,1.21,0.22,1,1,1]}}
            }
        }
        Item {
            id:viewport;x:40;y:98;width:parent.width-80;height:parent.height-114;clip:true
            property real scrollX:window.currentTab===0 ? 0:window.currentTab===1 ? dash.width+16:window.currentTab===2 ? dash.width+media.width+32:dash.width+media.width+performance.width+48
            Behavior on scrollX{NumberAnimation{id:pageAnimation;duration:500;easing.type:Easing.BezierSpline;easing.bezierCurve:[0.38,1.21,0.22,1,1,1]}}
            Row {
                x:-viewport.scrollX;spacing:16
                DashboardPage{id:dash;width:implicitWidth;height:implicitHeight;backend:systemBackend;theme:window.shellPalette;active:panel.visible && (window.currentTab===0 || pageAnimation.running);onNavigateRequested:page=>window.selectTab(page)}
                MediaPage{id:media;width:implicitWidth;height:implicitHeight;backend:systemBackend;theme:window.shellPalette;active:panel.visible && (window.currentTab===1 || pageAnimation.running)}
                PerformancePage{id:performance;width:implicitWidth;height:implicitHeight;backend:systemBackend;theme:window.shellPalette}
                WeatherPage{id:weather;width:implicitWidth;height:implicitHeight;backend:systemBackend;theme:window.shellPalette}
            }
        }
    }
}
