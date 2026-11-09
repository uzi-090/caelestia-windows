import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import ".."

Item {
    id: root
    property var backend
    property var theme: ({card:"#29282d",cardAlt:"#39373f",foreground:"#e8e3ed",muted:"#bdb8c6",primary:"#cec4ff",secondary:"#c5c5e0",tertiary:"#e7b7d3",outline:"#4f4b58",onPrimary:"#302650"})
    property real unit:1
    property bool active:true
    readonly property var media:backend && backend.data ? backend.data.media || {} : ({})
    readonly property var lyrics:backend && backend.data ? backend.data.lyrics || ({state:"idle",lines:[],plainText:"",source:"",trackKey:"",error:""}) : ({state:"idle",lines:[],plainText:"",source:"",trackKey:"",error:""})
    property real phase:0
    property real scrubValue:-1
    readonly property real progress:scrubValue>=0 ? scrubValue : (media.duration>0 ? Math.min(1,media.position/media.duration):0)
    signal navigateRequested(int page)
    implicitWidth:1000
    implicitHeight:320
    function timeLabel(s) {s=Math.max(0,Math.floor(Number(s || 0)));return Math.floor(s/60)+":"+(s%60<10 ? "0":"")+s%60}
    NumberAnimation on phase {id:phaseAnimation;from:0;to:Math.PI*2;duration:2000;loops:Animation.Infinite;running:root.visible && root.active;paused:phaseAnimation.running && !(root.media.playing || false);easing.type:Easing.Linear}
    onPhaseChanged:scrubber.requestPaint()
    onProgressChanged:scrubber.requestPaint()
    onThemeChanged:scrubber.requestPaint()

    Item {
        id:backgroundShapes
        anchors.fill:parent;clip:true
        readonly property var shapePool:typeof backgroundShapePaths!=="undefined" ? backgroundShapePaths : [
            "M0 100 C0 44.772 44.772 0 100 0 C155.228 0 200 44.772 200 100 C200 155.228 155.228 200 100 200 C44.772 200 0 155.228 0 100 Z",
            shapeCookie9.path,shapeCookie12.path,
            "M100 4 L196 100 L100 196 L4 100 Z",
            "M90 10 Q100 -2 110 10 L194 174 Q204 194 184 194 H16 Q-4 194 6 174 Z",
            "M50 0 H150 Q200 0 200 50 V150 Q200 200 150 200 H50 Q0 200 0 150 V50 Q0 0 50 0 Z",
            "M0 80 Q0 0 80 0 H120 Q200 0 200 80 V190 Q200 200 190 200 H10 Q0 200 0 190 Z",
            "M0 100 C0 72 45 50 100 50 C155 50 200 72 200 100 C200 128 155 150 100 150 C45 150 0 128 0 100 Z"
        ]
        readonly property var colours:[root.theme.primaryContainer || Qt.darker(root.theme.primary,2.8),root.theme.secondaryContainer || Qt.darker(root.theme.secondary,2.8),root.theme.tertiaryContainer || Qt.darker(root.theme.tertiary,2.8),root.theme.outline]
        function rand(min,max){return min+Math.random()*(max-min)}
        function signedRand(min,max){return rand(min,max)*(Math.random()<0.5 ? -1:1)}
        Repeater {
            id:driftingShapes;model:14
            Item {
                id:drifter
                required property int index
                property real vx:backgroundShapes.signedRand(4,18)
                property real vy:backgroundShapes.signedRand(4,18)
                property real vr:backgroundShapes.rand(-12,12)
                readonly property int colourIndex:Math.floor(Math.random()*4)
                readonly property string svgPath:backgroundShapes.shapePool[Math.floor(Math.random()*backgroundShapes.shapePool.length)]
                width:36+index/14*(124-36);height:width
                opacity:[0.16,0.16,0.04,0.16][colourIndex]
                rotation:backgroundShapes.rand(0,360)
                Component.onCompleted:{x=backgroundShapes.rand(0,backgroundShapes.width-width);y=backgroundShapes.rand(0,backgroundShapes.height-height)}
                Shape {
                    anchors.fill:parent;preferredRendererType:Shape.CurveRenderer
                    transform:Scale{xScale:drifter.width/200;yScale:drifter.height/200}
                    ShapePath {strokeWidth:-1;fillColor:backgroundShapes.colours[drifter.colourIndex];PathSvg{path:drifter.svgPath}
                        Behavior on fillColor {ColorAnimation{duration:400}}
                    }
                }
            }
        }
        FrameAnimation {
            running:root.visible && root.active && (root.media.playing || false)
            onTriggered:{
                const dt=frameTime;
                for(let i=0;i<driftingShapes.count;i++){
                    const s=driftingShapes.itemAt(i);if(!s)continue;
                    s.x+=s.vx*dt;s.y+=s.vy*dt;s.rotation+=s.vr*dt;
                    if(s.x+s.width<0)s.x=backgroundShapes.width;else if(s.x>backgroundShapes.width)s.x=-s.width;
                    if(s.y+s.height<0)s.y=backgroundShapes.height;else if(s.y>backgroundShapes.height)s.y=-s.height;
                }
            }
        }
    }
    MediaArt {x:16;y:16;width:300;height:288;theme:root.theme;coverUrl:root.media.artwork || "";levels:root.active && root.backend ? root.backend.audioLevels:[];playing:root.active && (root.media.playing || false)}
    Item {
        x:344;y:16;width:312;height:288
        Text {x:0;y:24;width:parent.width;text:root.media.title || "Nothing playing";font.family:"Rubik";font.pixelSize:28;color:root.theme.foreground;elide:Text.ElideRight}
        Text {x:0;y:67;width:parent.width;text:root.media.artist || (root.media.available ? "Unknown artist":"Play music or a video");font.family:"Rubik";font.pixelSize:20;color:root.theme.secondary;elide:Text.ElideRight}
        Text {x:0;y:100;width:parent.width;text:root.media.album || "";font.family:"Rubik";font.pixelSize:18;color:root.theme.secondary;elide:Text.ElideRight}
        Item {
            x:0;y:150;width:312;height:48
            Text {x:0;anchors.verticalCenter:parent.verticalCenter;text:root.timeLabel(root.scrubValue>=0 ? root.scrubValue*root.media.duration:root.media.position);font.family:"Rubik";font.pixelSize:13;color:root.theme.foreground}
            Text {x:270;anchors.verticalCenter:parent.verticalCenter;width:42;horizontalAlignment:Text.AlignRight;text:root.timeLabel(root.media.duration);font.family:"Rubik";font.pixelSize:13;color:root.theme.foreground}
            Canvas {
                id:scrubber
                x:47;y:3;width:215;height:42;antialiasing:true
                onPaint:{
                    const c=getContext("2d");c.reset();c.lineCap="round";
                    const y=height/2, fullLength=width-8, filledWidth=fullLength*root.progress, handleX=filledWidth+6;
                    const fg=root.media.canSeek ? root.theme.primary:Qt.alpha(root.theme.foreground,0.38);
                    const bg=root.media.canSeek ? root.theme.outline:Qt.alpha(root.theme.foreground,0.1);
                    if(filledWidth+12<width-6){c.strokeStyle=bg;c.lineWidth=12;c.beginPath();c.moveTo(filledWidth+16,y);c.lineTo(width-6,y);c.stroke()}
                    if(root.progress>0){c.strokeStyle=fg;c.lineWidth=8.4;c.beginPath();for(let x=0;x<=filledWidth;x++){const yy=y+Math.sin(5*Math.PI*2*x/fullLength+root.phase)*4.2;if(x===0)c.moveTo(x,yy);else c.lineTo(x,yy)}c.stroke()}
                    c.strokeStyle=fg;c.lineWidth=4;c.beginPath();c.moveTo(handleX,3);c.lineTo(handleX,height-3);c.stroke();
                    if(root.progress<0.96){c.fillStyle=fg;c.beginPath();c.arc(width-6,y,2,0,Math.PI*2);c.fill()}
                }
                MouseArea {
                    anchors.fill:parent;enabled:root.media.canSeek || false;cursorShape:Qt.PointingHandCursor
                    onPressed:event=>{root.scrubValue=Math.max(0,Math.min(1,event.x/width))}
                    onPositionChanged:event=>{if(pressed)root.scrubValue=Math.max(0,Math.min(1,event.x/width))}
                    onReleased:{root.backend.seek(root.scrubValue*root.media.duration);root.scrubValue=-1}
                    onCanceled:root.scrubValue=-1
                }
            }
        }
        MediaButton {x:0;y:208;width:43;height:55;glyph:"shuffle";active:root.media.shuffle || false;enabled:root.media.canShuffle || false;onTriggered:root.backend.toggleShuffle()}
        MediaButton {x:49;y:208;width:53;height:55;glyph:"skip_previous";enabled:root.media.canPrevious || false;onTriggered:root.backend.previousTrack()}
        MediaButton {x:108;y:208;width:97;height:55;glyph:root.media.playing ? "pause":"play_arrow";primary:true;enabled:root.media.canPlayPause || false;onTriggered:root.backend.playPause()}
        MediaButton {x:211;y:208;width:53;height:55;glyph:"skip_next";enabled:root.media.canNext || false;onTriggered:root.backend.nextTrack()}
        MediaButton {x:270;y:208;width:42;height:55;glyph:root.media.repeat===2 ? "repeat_one":"repeat";active:Number(root.media.repeat || 0)>0;enabled:root.media.canRepeat || false;onTriggered:root.backend.cycleRepeat()}
    }
    Item {
        x:684;y:16;width:300;height:288
        Icon {x:0;y:7;name:"lyrics";size:22;color:root.theme.foreground}
        Text {x:31;y:7;text:"Lyrics";font.family:"Rubik";font.pixelSize:20;color:root.theme.foreground}
        Text {x:128;y:13;width:118;text:root.lyrics.source || "";font.family:"Rubik";font.pixelSize:11;color:root.theme.muted;horizontalAlignment:Text.AlignRight;renderType:Text.QtRendering}
        MediaButton {x:262;y:0;width:38;height:40;glyph:"more_vert";onTriggered:optionsMenu.open()}
        Menu {
            id:optionsMenu;objectName:"mediaOptions";x:180;y:43;width:200;padding:6;popupType:Popup.Window
            background:Rectangle {radius:14;color:root.theme.cardAlt;border.width:1;border.color:root.theme.outline}
            MenuItem {
                id:refreshItem;text:"Refresh media";implicitHeight:40;font.family:"Rubik";font.pixelSize:14
                contentItem:Text {text:refreshItem.text;font:refreshItem.font;color:root.theme.foreground;verticalAlignment:Text.AlignVCenter;leftPadding:9;rightPadding:9}
                background:Rectangle {radius:9;color:refreshItem.highlighted ? Qt.alpha(root.theme.primary,0.15):"transparent"}
                onTriggered:if(root.backend)root.backend.refresh()
            }
        }
        LyricsPane {
            id:lyricsPane;objectName:"lyricsPane"
            x:0;y:55;width:300;height:174
            theme:root.theme;lyrics:root.lyrics;position:Number(root.media.position || 0)
            active:root.active && root.visible;canSeek:root.media.canSeek || false
            onSeekRequested:seconds=>{if(root.backend)root.backend.seek(seconds)}
        }
        Rectangle {
            x:0;y:248;width:300;height:40;radius:20;color:root.theme.cardAlt
            Icon {x:17;anchors.verticalCenter:parent.verticalCenter;name:"select_window";size:19;color:root.theme.secondary}
            Text {x:45;anchors.verticalCenter:parent.verticalCenter;width:212;text:root.media.appName || "No media player";font.family:"Rubik";font.pixelSize:14;color:root.theme.secondary;elide:Text.ElideRight;horizontalAlignment:Text.AlignHCenter}
            Rectangle {x:258;y:0;width:1;height:40;color:root.theme.outline}
            Icon {x:268;anchors.verticalCenter:parent.verticalCenter;name:"expand_more";size:22;color:root.theme.secondary}
            MouseArea {anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:sessionMenu.open()}
            Menu {
                id:sessionMenu;objectName:"mediaSessions";y:43;width:300;padding:6;popupType:Popup.Window
                background:Rectangle {radius:14;color:root.theme.cardAlt;border.width:1;border.color:root.theme.outline}
                Repeater {
                    model:root.media.sessions || []
                    MenuItem {
                        id:sessionItem;required property var modelData;text:modelData.name || modelData.id;checkable:true;checked:modelData.id===root.media.sessionId;implicitHeight:40;font.family:"Rubik";font.pixelSize:14
                        contentItem:Text {text:sessionItem.text;font:sessionItem.font;color:root.theme.foreground;verticalAlignment:Text.AlignVCenter;leftPadding:30;rightPadding:8;elide:Text.ElideRight}
                        indicator:Icon {x:10;anchors.verticalCenter:parent.verticalCenter;name:"check";size:18;color:root.theme.primary;visible:sessionItem.checked}
                        background:Rectangle {radius:9;color:sessionItem.highlighted ? Qt.alpha(root.theme.primary,0.15):"transparent"}
                        onTriggered:root.backend.selectSession(modelData.id)
                    }
                }
            }
        }
    }
    component MediaButton: Rectangle {
        id:button
        property string glyph
        property bool primary:false
        property bool active:false
        signal triggered()
        radius:primary ? 14 : height/2;color:primary || active ? root.theme.primary : root.theme.cardAlt;opacity:enabled ? 1 : 0.4
        scale:mouse.pressed ? 0.93 : 1
        Behavior on radius {NumberAnimation{duration:200;easing.type:Easing.OutCubic}}
        Behavior on scale {NumberAnimation{duration:150;easing.type:Easing.OutCubic}}
        Icon {anchors.centerIn:parent;name:button.glyph;size:button.primary ? 31:25;color:button.primary || button.active ? root.theme.onPrimary : root.theme.secondary}
        Rectangle {anchors.fill:parent;radius:parent.radius;color:root.theme.foreground;opacity:mouse.containsMouse ? 0.08:0;Behavior on opacity{NumberAnimation{duration:150}}}
        MouseArea {id:mouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:button.triggered()}
    }
}
