import QtQuick
import QtQuick.Controls
import ".."

Item {
    id: root
    property var backend
    property var theme: ({card:"#29282d",cardAlt:"#39373f",foreground:"#e8e3ed",muted:"#bdb8c6",primary:"#cec4ff",secondary:"#c5c5e0",tertiary:"#e7b7d3",outline:"#4f4b58",onPrimary:"#302650"})
    property real unit: 1
    property bool active: true
    readonly property var system: backend && backend.data ? backend.data.system || {} : ({})
    readonly property var media: backend && backend.data ? backend.data.media || {} : ({})
    readonly property var weather: backend && backend.data ? backend.data.weather || {} : ({})
    property date now: new Date()
    property date month: new Date(now.getFullYear(),now.getMonth(),1)
    property real calendarOpacity: 1
    property real calendarShift: 0
    property int monthDelta: 0
    signal navigateRequested(int page)
    implicitWidth: 839
    implicitHeight: 435

    function uptimeText() {
        const n = Math.max(0,Math.floor(Number(system.uptime || 0)));
        const h = Math.floor(n / 3600), m = Math.floor(n % 3600 / 60);
        return h >= 24 ? Math.floor(h / 24)+" days, "+h%24+" hours" : h+" hours, "+m+" minutes";
    }
    function calendarDate(index) {
        return new Date(month.getFullYear(),month.getMonth(),1-month.getDay()+index);
    }
    function changeMonth(delta) {
        if (outAnimation.running || inAnimation.running) return;
        monthDelta=delta;
        outAnimation.start();
    }
    Timer { interval:1000;repeat:true;running:true;onTriggered:root.now=new Date() }
    SequentialAnimation {
        id: outAnimation
        ParallelAnimation {
            NumberAnimation {target:root;property:"calendarOpacity";to:0;duration:150;easing.type:Easing.OutCubic}
            NumberAnimation {target:root;property:"calendarShift";to:-root.monthDelta*28;duration:350;easing.type:Easing.BezierSpline;easing.bezierCurve:[0.42,1.67,0.21,0.9,1,1]}
        }
        ScriptAction {script:{root.month=new Date(root.month.getFullYear(),root.month.getMonth()+root.monthDelta,1);root.calendarShift=root.monthDelta*28;inAnimation.start()}}
    }
    ParallelAnimation {
        id: inAnimation
        NumberAnimation {target:root;property:"calendarOpacity";to:1;duration:200;easing.type:Easing.OutCubic}
        NumberAnimation {target:root;property:"calendarShift";to:0;duration:500;easing.type:Easing.BezierSpline;easing.bezierCurve:[0.38,1.21,0.22,1,1,1]}
    }

    GlassWidget {
        x:0;y:0;width:275;height:130;radius:42;surfaceColor:root.theme.card;highlightColor:root.theme.foreground
        MouseArea {anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:root.navigateRequested(3)}
        Icon {x:25;y:30;width:72;height:72;name:root.weather.icon || "partly_cloudy_day";size:72;color:root.theme.secondary}
        Text {x:132;y:31;width:135;text:root.weather.available ? Math.round(root.weather.temperature)+"°C" : "—°C";font.family:"Rubik";font.pixelSize:33;font.weight:Font.Medium;color:root.theme.primary}
        Text {x:133;y:80;width:130;text:root.weather.condition || "Loading weather";font.family:"Rubik";font.pixelSize:13;color:root.theme.muted;elide:Text.ElideRight}
    }
    GlassWidget {
        x:287;y:0;width:340;height:130;radius:28;surfaceColor:root.theme.card;highlightColor:root.theme.foreground
        Rectangle {x:57;y:16;width:97;height:97;radius:48;color:root.theme.cardAlt
            Icon {anchors.centerIn:parent;name:"person_add";size:44;color:root.theme.secondary}
        }
        Rectangle {x:23;y:17;width:46;height:46;radius:12;rotation:20;color:Qt.alpha(root.theme.primary,0.34)
            Icon {anchors.centerIn:parent;rotation:-20;name:"window";size:31;color:root.theme.primary}
        }
        Rectangle {x:163;y:18;width:139;height:38;radius:20;color:root.theme.cardAlt
            Icon {x:13;anchors.verticalCenter:parent.verticalCenter;name:"select_window";size:17;color:root.theme.secondary}
            Text {x:37;anchors.verticalCenter:parent.verticalCenter;width:90;text:"Windows 11…";font.family:"Rubik";font.pixelSize:13;font.italic:true;color:root.theme.secondary;elide:Text.ElideRight}
        }
        Rectangle {x:166;y:58;width:13;height:13;radius:7;color:root.theme.cardAlt}
        Rectangle {x:153;y:73;width:9;height:9;radius:5;color:root.theme.cardAlt}
        Rectangle {x:126;y:83;width:47;height:32;radius:17;color:root.theme.tertiary
            Icon {anchors.centerIn:parent;name:"clock_arrow_up";size:23;color:root.theme.onPrimary}
        }
        Text {x:181;y:91;width:147;text:"up "+root.uptimeText();font.family:"Rubik";font.pixelSize:13;color:root.theme.foreground;elide:Text.ElideRight}
    }
    GlassWidget {
        x:0;y:142;width:110;height:293;radius:16;surfaceColor:root.theme.card;highlightColor:root.theme.foreground
        Column {
            anchors.centerIn:parent;spacing:-2
            Text {anchors.horizontalCenter:parent.horizontalCenter;text:("0"+(root.now.getHours()%12 || 12)).slice(-2);font.family:"Rubik";font.pixelSize:36;font.weight:Font.DemiBold;color:root.theme.secondary}
            Text {anchors.horizontalCenter:parent.horizontalCenter;text:"•••";font.family:"Rubik";font.pixelSize:26;color:root.theme.primary}
            Text {anchors.horizontalCenter:parent.horizontalCenter;text:Qt.formatDateTime(root.now,"mm");font.family:"Rubik";font.pixelSize:36;font.weight:Font.DemiBold;color:root.theme.secondary}
            Text {anchors.horizontalCenter:parent.horizontalCenter;text:Qt.formatDateTime(root.now,"AP");font.family:"Rubik";font.pixelSize:23;font.weight:Font.Medium;color:root.theme.primary}
        }
    }
    GlassWidget {
        x:122;y:142;width:376;height:293;radius:28;surfaceColor:root.theme.card;highlightColor:root.theme.foreground;clip:true
        Item {
            x:16;y:14;width:344;height:38
            PageButton {x:0;width:32;height:32;glyph:"chevron_left";backgroundColor:"transparent";onTriggered:root.changeMonth(-1)}
            Text {x:40;width:264;anchors.verticalCenter:parent.verticalCenter;horizontalAlignment:Text.AlignHCenter;text:Qt.formatDate(root.month,"MMMM yyyy");font.family:"Rubik";font.pixelSize:18;color:root.theme.primary;opacity:root.calendarOpacity}
            PageButton {x:312;width:32;height:32;glyph:"chevron_right";backgroundColor:"transparent";onTriggered:root.changeMonth(1)}
        }
        Row {
            x:16;y:62;width:344;height:24
            Repeater {model:["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
                Text {required property int index;required property string modelData;width:344/7;text:modelData;horizontalAlignment:Text.AlignHCenter;font.family:"Rubik";font.pixelSize:14;color:index===0 || index===6 ? root.theme.tertiary : root.theme.foreground}
            }
        }
        Grid {
            x:16+root.calendarShift;y:91;width:344;height:188;columns:7;opacity:root.calendarOpacity
            Repeater {
                model:42
                Item {
                    id: dayCell
                    required property int index
                    readonly property date cellDate:root.calendarDate(index)
                    readonly property bool today:cellDate.toDateString()===root.now.toDateString()
                    width:344/7;height:31
                    Canvas {
                        id:dayHighlight
                        anchors.centerIn:parent;width:36;height:36;visible:dayCell.today
                        onPaint:{const c=getContext("2d");c.reset();c.fillStyle=root.theme.primary;c.beginPath();for(let i=0;i<=120;i++){const a=i/120*Math.PI*2;const r=15*(1+0.1*Math.cos(8*a));const xx=18+r*Math.cos(a), yy=18+r*Math.sin(a);if(i===0)c.moveTo(xx,yy);else c.lineTo(xx,yy);}c.closePath();c.fill()}
                        Connections {target:root;function onThemeChanged(){dayHighlight.requestPaint()}}
                    }
                    Text {anchors.centerIn:parent;text:dayCell.cellDate.getDate();font.family:"Rubik";font.pixelSize:14;color:dayCell.today ? root.theme.onPrimary : (dayCell.cellDate.getDay()===0 || dayCell.cellDate.getDay()===6 ? root.theme.tertiary : root.theme.muted);opacity:dayCell.cellDate.getMonth()===root.month.getMonth() ? 1 : 0.38}
                }
            }
        }
        MouseArea {anchors.fill:parent;acceptedButtons:Qt.MiddleButton;onClicked:root.month=new Date(root.now.getFullYear(),root.now.getMonth(),1);onWheel:event=>{root.changeMonth(event.angleDelta.y>0 ? -1:1);event.accepted=true}}
    }
    GlassWidget {
        x:510;y:142;width:117;height:293;radius:16;surfaceColor:root.theme.card;highlightColor:root.theme.foreground
        MouseArea {anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:root.navigateRequested(2)}
        Repeater {
            model:[{icon:"memory",value:root.system.cpuPercent || 0,accent:root.theme.primary},{icon:"memory_alt",value:root.system.memoryPercent || 0,accent:root.theme.tertiary},{icon:"hard_drive",value:root.system.storagePercent || 0,accent:root.theme.secondary}]
            Item {required property int index;required property var modelData;x:17;y:15+index*90;width:83;height:83
                ArcGauge {anchors.fill:parent;value:parent.modelData.value;strokeColor:parent.modelData.accent;trackColor:root.theme.outline;lineWidth:6}
                Icon {anchors.centerIn:parent;name:parent.modelData.icon;size:29;color:parent.modelData.accent}
            }
        }
    }
    Rectangle {
        x:639;y:0;width:200;height:435;radius:56;color:root.theme.card
        MediaArt {x:18;y:18;width:164;height:164;compact:true;theme:root.theme;progress:root.media.duration>0 ? root.media.position/root.media.duration:0;coverUrl:root.media.artwork || "";levels:[];playing:root.active && (root.media.playing || false)}
        Text {x:18;y:195;width:164;text:root.media.title || "No media";font.family:"Rubik";font.pixelSize:17;font.weight:Font.Medium;color:root.theme.primary;horizontalAlignment:Text.AlignHCenter;elide:Text.ElideRight}
        Text {x:18;y:225;width:164;text:root.media.album || (root.media.available ? "" : "Play something");font.family:"Rubik";font.pixelSize:13;color:root.theme.muted;horizontalAlignment:Text.AlignHCenter;elide:Text.ElideRight}
        Text {x:18;y:252;width:164;text:root.media.artist || (root.media.available ? "" : "on your device");font.family:"Rubik";font.pixelSize:14;color:root.theme.secondary;horizontalAlignment:Text.AlignHCenter;elide:Text.ElideRight}
        PageButton {x:18;y:282;width:44;height:44;glyph:"skip_previous";enabled:root.media.canPrevious || false;onTriggered:root.backend.previousTrack()}
        PageButton {x:68;y:282;width:64;height:44;glyph:root.media.playing ? "pause" : "play_arrow";primary:true;enabled:root.media.canPlayPause || false;onTriggered:root.backend.playPause()}
        PageButton {x:138;y:282;width:44;height:44;glyph:"skip_next";enabled:root.media.canNext || false;onTriggered:root.backend.nextTrack()}
        AnimatedImage {x:31;y:344;width:138;height:67;source:Qt.resolvedUrl("../../assets/bongocat.gif");playing:root.active && (root.media.playing || false);fillMode:Image.PreserveAspectFit;asynchronous:true}
        MouseArea {x:0;y:185;width:parent.width;height:90;cursorShape:Qt.PointingHandCursor;onClicked:root.navigateRequested(1)}
    }
    component PageButton: Rectangle {
        id:button
        property string glyph
        property bool primary:false
        property color backgroundColor:primary ? root.theme.primary : root.theme.cardAlt
        signal triggered()
        radius:height/2;color:backgroundColor;opacity:enabled ? 1 : 0.42
        scale:buttonMouse.pressed ? 0.93 : 1
        Behavior on scale {NumberAnimation {duration:150;easing.type:Easing.OutCubic}}
        Icon {anchors.centerIn:parent;name:button.glyph;size:24;color:button.primary ? root.theme.onPrimary : root.theme.secondary}
        Rectangle {anchors.fill:parent;radius:parent.radius;color:root.theme.foreground;opacity:buttonMouse.containsMouse ? 0.08 : 0;Behavior on opacity {NumberAnimation{duration:150}}}
        MouseArea {id:buttonMouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:button.triggered()}
    }
}
