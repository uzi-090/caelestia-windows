import QtQuick
import QtQuick.Controls

Item {
    id: root
    property var theme: ({foreground:"#eee9f0",muted:"#bdb7c7",primary:"#cec4ff",cardAlt:"#35313c"})
    property var lyrics: ({state:"idle",lines:[],plainText:"",source:"",trackKey:"",error:""})
    property real position: 0
    property bool active: true
    property bool canSeek: false
    property int currentIndex: -1
    property bool following: true
    property var syncedLines: []
    property string plainText: ""
    property string _contentKey: ""
    property bool _ready: false
    readonly property string lyricState: lyrics && lyrics.state ? lyrics.state : "idle"
    readonly property bool hasSynced: lyricState === "synced" && syncedLines.length > 0
    readonly property bool hasPlain: lyricState === "plain" && plainText.length > 0
    readonly property real scrollPosition: syncedView.contentY
    readonly property bool scrolling: scrollAnimation.running
    signal seekRequested(real seconds)
    implicitWidth: 300
    implicitHeight: 174

    function consumeLyrics() {
        if (!_ready) return;
        const payload = lyrics || {};
        const lines = payload.lines && typeof payload.lines.length==="number" ? Array.from(payload.lines) : [];
        const text = String(payload.plainText || "");
        const key = String(payload.trackKey || "")+"|"+lyricState+"|"+JSON.stringify(lines)+"|"+text;
        if (key === _contentKey) { updateCurrent(true); return; }
        _contentKey = key;
        scrollAnimation.stop();
        returnTimer.stop();
        following = true;
        currentIndex = -1;
        syncedLines = lines.filter(line => line && Number.isFinite(Number(line.time)))
            .map(line => ({time:Math.max(0,Number(line.time)),text:String(line.text || "")}))
            .sort((a,b) => a.time-b.time);
        plainText = text;
        syncedView.contentY = 0;
        plainView.contentY = 0;
        Qt.callLater(() => updateCurrent(false));
    }

    function indexForTime(seconds) {
        let low=0, high=syncedLines.length-1, found=-1;
        while (low<=high) {
            const middle=(low+high)>>1;
            if (syncedLines[middle].time<=seconds) {found=middle;low=middle+1;}
            else high=middle-1;
        }
        return found;
    }

    function updateCurrent(animate) {
        if (!_ready || !active || !visible || !hasSynced) return;
        const next=indexForTime(Math.max(0,Number(position || 0)));
        const changed=next!==currentIndex;
        currentIndex=next;
        if (following && (changed || !animate)) centerCurrent(animate && changed);
    }

    function centerCurrent(animate) {
        if (!active || !visible || !hasSynced || !following) return;
        lyricColumn.forceLayout();
        const line=lineRepeater.itemAt(Math.max(0,currentIndex));
        if (!line) return;
        const maximum=Math.max(0,syncedView.contentHeight-syncedView.height);
        const target=Math.max(0,Math.min(maximum,lyricColumn.y+line.y+line.height/2-syncedView.height/2));
        syncedView.cancelFlick();
        scrollAnimation.stop();
        if (animate && Math.abs(target-syncedView.contentY)>0.5) {
            scrollAnimation.from=syncedView.contentY;
            scrollAnimation.to=target;
            scrollAnimation.start();
        } else syncedView.contentY=target;
    }

    function pauseFollowing() {
        if (!hasSynced) return;
        following=false;
        scrollAnimation.stop();
        returnTimer.restart();
    }

    function resumeFollowing() {
        following=true;
        returnTimer.stop();
        updateCurrent(true);
        centerCurrent(true);
    }

    function seekLine(index) {
        if (!canSeek || index<0 || index>=syncedLines.length) return;
        seekRequested(syncedLines[index].time);
        resumeFollowing();
    }

    function wheelScroll(view,event) {
        const delta=event.pixelDelta.y!==0 ? event.pixelDelta.y:event.angleDelta.y/120*42;
        view.cancelFlick();
        view.contentY=Math.max(0,Math.min(Math.max(0,view.contentHeight-view.height),view.contentY-delta));
        event.accepted=true;
    }

    onLyricsChanged: consumeLyrics()
    onPositionChanged: updateCurrent(true)
    onHeightChanged: if (_ready) Qt.callLater(() => centerCurrent(false))
    onWidthChanged: if (_ready) Qt.callLater(() => centerCurrent(false))
    onActiveChanged: {
        if (!_ready) return;
        if (active) {following=true;Qt.callLater(() => updateCurrent(false));}
        else {scrollAnimation.stop();returnTimer.stop();}
    }
    onVisibleChanged: {
        if (!_ready) return;
        if (visible && active) Qt.callLater(() => updateCurrent(false));
        else scrollAnimation.stop();
    }
    Component.onCompleted: {_ready=true;consumeLyrics();}

    Timer {id:returnTimer;interval:6000;onTriggered:root.resumeFollowing()}
    NumberAnimation {
        id:scrollAnimation;target:syncedView;property:"contentY";duration:380
        easing.type:Easing.BezierSpline;easing.bezierCurve:[0.2,0,0,1,1,1]
    }

    Flickable {
        id:syncedView
        anchors.fill:parent
        contentWidth:width;contentHeight:lyricColumn.height+height
        clip:true;boundsBehavior:Flickable.StopAtBounds
        flickableDirection:Flickable.VerticalFlick
        opacity:root.hasSynced ? 1:0;visible:opacity>0;enabled:root.hasSynced
        Behavior on opacity {NumberAnimation{duration:220;easing.type:Easing.OutCubic}}
        onDraggingChanged:if(dragging)root.pauseFollowing()
        onMovementEnded:if(!root.following)returnTimer.restart()
        WheelHandler {target:null;onWheel:event=>{root.pauseFollowing();root.wheelScroll(syncedView,event)}}
        Column {
            id:lyricColumn;x:8;y:syncedView.height/2;width:syncedView.width-16;spacing:10
            Repeater {
                id:lineRepeater;model:root.syncedLines
                Item {
                    id:lyricLine
                    required property int index
                    required property var modelData
                    readonly property bool selected:index===root.currentIndex
                    readonly property int distance:Math.abs(index-root.currentIndex)
                    width:lyricColumn.width;height:lineText.implicitHeight+8
                    opacity:selected ? 1:!root.following ? 0.78:distance<=1 ? 0.60:distance===2 ? 0.34:0.18
                    Behavior on opacity {NumberAnimation{duration:220;easing.type:Easing.OutCubic}}
                    Text {
                        id:lineText;anchors.centerIn:parent;width:parent.width
                        text:lyricLine.modelData.text || "· · ·"
                        font.family:"Rubik";font.pixelSize:18;font.weight:lyricLine.selected ? Font.DemiBold:Font.Normal
                        color:lyricLine.selected ? root.theme.primary:root.theme.muted
                        horizontalAlignment:Text.AlignHCenter;wrapMode:Text.WrapAtWordBoundaryOrAnywhere
                        lineHeight:1.3;renderType:Text.QtRendering
                        Behavior on color {ColorAnimation{duration:220}}
                    }
                    MouseArea {anchors.fill:parent;enabled:root.canSeek;cursorShape:Qt.PointingHandCursor;onClicked:root.seekLine(lyricLine.index)}
                }
            }
        }
    }

    Text {
        x:0;y:0;width:parent.width;height:20
        text:"Untimed lyrics";visible:root.hasPlain;font.family:"Rubik";font.pixelSize:12
        color:root.theme.muted;horizontalAlignment:Text.AlignHCenter;renderType:Text.QtRendering
    }
    Flickable {
        id:plainView;x:0;y:24;width:parent.width;height:parent.height-24
        contentWidth:width;contentHeight:plainLyrics.implicitHeight+12
        clip:true;boundsBehavior:Flickable.StopAtBounds;flickableDirection:Flickable.VerticalFlick
        opacity:root.hasPlain ? 1:0;visible:opacity>0;enabled:root.hasPlain
        Behavior on opacity {NumberAnimation{duration:220;easing.type:Easing.OutCubic}}
        WheelHandler {target:null;onWheel:event=>root.wheelScroll(plainView,event)}
        Text {
            id:plainLyrics;x:8;y:4;width:parent.width-16;text:root.plainText
            font.family:"Rubik";font.pixelSize:18;color:root.theme.foreground
            horizontalAlignment:Text.AlignHCenter;wrapMode:Text.WrapAtWordBoundaryOrAnywhere
            lineHeight:1.5;renderType:Text.QtRendering
        }
    }

    Rectangle {
        anchors.top:parent.top;anchors.right:parent.right;width:84;height:28;radius:14
        color:root.theme.cardAlt;visible:root.hasSynced && !root.following;z:2
        Icon {x:8;anchors.verticalCenter:parent.verticalCenter;name:"my_location";size:16;color:root.theme.primary}
        Text {x:30;anchors.verticalCenter:parent.verticalCenter;text:"Follow";font.family:"Rubik";font.pixelSize:12;color:root.theme.foreground;renderType:Text.QtRendering}
        MouseArea {anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:root.resumeFollowing()}
    }

    Item {
        anchors.fill:parent
        opacity:!root.hasSynced && !root.hasPlain ? 1:0;visible:opacity>0
        Behavior on opacity {NumberAnimation{duration:220;easing.type:Easing.OutCubic}}
        Column {
            anchors.centerIn:parent;width:parent.width-16;spacing:13
            Icon {
                id:statusIcon;anchors.horizontalCenter:parent.horizontalCenter;size:40
                name:root.lyricState==="loading" ? "progress_activity":root.lyricState==="instrumental" ? "graphic_eq":root.lyricState==="error" ? "cloud_off":"lyrics"
                color:root.theme.muted;opacity:0.75
                NumberAnimation on rotation {from:0;to:360;duration:1400;loops:Animation.Infinite;running:root.active && root.visible && root.lyricState==="loading";easing.type:Easing.Linear}
            }
            Text {
                width:parent.width
                text:root.lyricState==="loading" ? "Finding lyrics…":root.lyricState==="instrumental" ? "Instrumental":root.lyricState==="error" ? "Unable to load lyrics":root.lyricState==="idle" ? "Play a song for lyrics":"No lyrics found"
                font.family:"Rubik";font.pixelSize:18;color:root.theme.muted
                horizontalAlignment:Text.AlignHCenter;wrapMode:Text.WrapAtWordBoundaryOrAnywhere;renderType:Text.QtRendering
            }
        }
    }
}
