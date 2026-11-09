import QtQuick
import QtQuick.Window
import QtQuick.Shapes
import QtQuick.Effects

Item {
    id: root
    property url coverUrl
    property var levels: []
    property bool playing: false
    property bool compact: false
    property var theme: wallpaper.data
    property real progress: 0
    property real turn: 360
    property real wavePhase: 0
    readonly property real coverSize: compact ? Math.min(width,height)*0.74 : Math.min(width,height)*0.694444
    readonly property var geometry: compact ? shapeCookie12 : shapeCookie9
    readonly property real radius: coverSize/2
    readonly property real deviceScale: Screen.devicePixelRatio * (root.Window.window ? root.Window.window.uiScale : 1)
    readonly property int coverPixels: Math.max(1,Math.ceil(coverSize*deviceScale))
    function edgeAt(angle) {
        const radii = geometry.radii;
        let t = ((angle - turn + 720)%360)/360*radii.length;
        let i = Math.floor(t)%radii.length;
        return (radii[i] + (radii[(i+1)%radii.length]-radii[i])*(t-Math.floor(t)))*coverSize;
    }
    NumberAnimation on turn {
        id:turnAnimation
        from:360;to:0;duration:23500;loops:Animation.Infinite
        running:root.visible;paused:turnAnimation.running && !root.playing;easing.type:Easing.Linear
    }
    NumberAnimation on wavePhase {
        id:waveAnimation
        from:0;to:Math.PI*2;duration:2000;loops:Animation.Infinite
        running:root.visible;paused:waveAnimation.running && !root.playing
    }
    onWavePhaseChanged:compactArc.requestPaint()
    onProgressChanged:compactArc.requestPaint()
    Repeater {
        model:root.compact ? 0:60
        delegate: Rectangle {
            id:bar
            required property int index
            readonly property real angle:index*360/60-90
            readonly property real magnitude:Math.max(0.01,Math.min(1,root.levels[index] || 0))
            readonly property real edge:root.edgeAt(angle)+14
            readonly property real length:magnitude*Math.max(2,(root.width-root.coverSize)/2-12)
            x:root.width/2+Math.cos(angle*Math.PI/180)*(edge+length/2)-width/2
            y:root.height/2+Math.sin(angle*Math.PI/180)*(edge+length/2)-height/2
            width:4;height:length;radius:width/2;color:root.theme.primary
            rotation:angle+90
        }
    }
    Canvas {
        id:compactArc;anchors.fill:parent;visible:root.compact;antialiasing:true
        onPaint:{
            let c=getContext("2d");c.reset();c.lineCap="round";
            const r=Math.min(width,height)/2-6,cx=width/2,cy=height/2;
            const end=Math.max(0.02,root.progress)*Math.PI;
            if(end+0.1<Math.PI){c.strokeStyle=root.theme.outline;c.lineWidth=6;c.beginPath();c.arc(cx,cy,r,-Math.PI+end+0.1,0);c.stroke();}
            c.strokeStyle=root.theme.primary;c.lineWidth=6;c.beginPath();
            for(let t=0;t<=end;t+=0.012){let a=t-Math.PI,rr=r+Math.sin(t*16+root.wavePhase)*3;let x=cx+Math.cos(a)*rr,y=cy+Math.sin(a)*rr;if(t===0)c.moveTo(x,y);else c.lineTo(x,y)}c.stroke();
        }
    }
    Item {
        id:cover;anchors.centerIn:parent;width:root.coverSize;height:width
        Item {
            id:maskShape;anchors.fill:parent;visible:false;layer.enabled:true
            layer.textureSize:Qt.size(root.coverPixels,root.coverPixels)
            layer.smooth:true
            Shape {
                anchors.centerIn:parent;width:200;height:200
                scale:cover.width/200;rotation:root.turn
                preferredRendererType:Shape.CurveRenderer
                ShapePath {strokeWidth:-1;fillColor:"white";PathSvg{path:root.geometry.path}}
            }
        }
        Shape {
            anchors.centerIn:parent;width:200;height:200
            preferredRendererType:Shape.CurveRenderer
            scale:cover.width/200
            rotation:root.turn
            ShapePath{strokeWidth:-1;fillColor:root.theme.cardAlt;PathSvg{path:root.geometry.path}}
        }
        Image {
            id:art;anchors.fill:parent;source:root.coverUrl;fillMode:Image.PreserveAspectCrop;asynchronous:true
            sourceSize:Qt.size(768,768)
            smooth:true;mipmap:true
            layer.enabled:true;layer.effect:MultiEffect{maskEnabled:true;maskSource:maskShape;maskThresholdMin:0.5;maskSpreadAtMin:1}
            layer.textureSize:Qt.size(root.coverPixels,root.coverPixels)
            layer.smooth:true;layer.mipmap:true
            opacity:status===Image.Ready ? 1:0
            Behavior on opacity {NumberAnimation{duration:400}}
        }
        Icon {anchors.centerIn:parent;name:"music_note";size:root.coverSize*0.34;color:root.theme.primary;visible:art.status!==Image.Ready}
    }
}
