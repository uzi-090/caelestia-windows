import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import ".."

Item {
    id:root
    property var backend
    property var theme:({card:"#29282d",cardAlt:"#39373f",foreground:"#e8e3ed",muted:"#bdb8c6",primary:"#cec4ff",secondary:"#c5c5e0",tertiary:"#e7b7d3",outline:"#4f4b58",onPrimary:"#302650"})
    property real unit:1
    readonly property var system:backend && backend.data ? backend.data.system || {} : ({})
    readonly property var drive:(system.drives || []).find(d=>d.id===system.selectedDrive) || (system.drives || [])[0] || ({})
    readonly property color moduleSurface:Qt.alpha(Qt.tint(theme.card,Qt.alpha(theme.foreground,0.035)),0.88)
    readonly property color subtleEdge:Qt.alpha(theme.foreground,0.075)
    readonly property color gaugeTrack:Qt.alpha(theme.outline,0.62)
    signal navigateRequested(int page)
    implicitWidth:1112
    implicitHeight:380
    function usage(used,total){return (Number(used || 0)/1073741824).toFixed(1)+" / "+(Number(total || 0)/1073741824).toFixed(1)+" GiB"}
    function bytes(n){n=Number(n || 0);const u=["B","KiB","MiB","GiB","TiB"];let i=0;while(n>=1024 && i<4){n/=1024;i++}return n.toFixed(i===0 ? 0:1)+" "+u[i]}

    GlassWidget {
        x:0;y:0;width:950;height:148;radius:22;surfaceColor:root.moduleSurface;highlightColor:root.theme.foreground
        ArcGauge {x:20;y:18;width:46;height:46;value:root.system.cpuPercent || 0;strokeColor:root.theme.primary;trackColor:root.gaugeTrack;lineWidth:3.5}
        Icon {x:31;y:29;width:24;height:24;name:"memory";size:24;color:root.theme.primary}
        Text {x:82;y:19;width:700;text:"CPU";font.family:"Rubik";font.pixelSize:21;color:root.theme.primary}
        Text {x:82;y:50;width:700;text:root.system.cpuName || "Processor";font.family:"Rubik";font.pixelSize:14;color:root.theme.muted;elide:Text.ElideRight}
        Icon {x:21;y:96;name:"thermometer";size:20;color:root.theme.primary}
        Text {x:45;y:97;text:Number(root.system.temperature)>=0 ? Math.round(root.system.temperature)+"°C":"—°C";font.family:"Rubik";font.pixelSize:15;color:root.theme.foreground}
        Rectangle {x:24;y:122;width:176;height:5;radius:3;color:root.gaugeTrack
            Rectangle {width:Math.max(5,parent.width*Math.max(0,Math.min(100,Number(root.system.temperature || 0)))/100);height:parent.height;radius:3;color:root.theme.primary;visible:Number(root.system.temperature)>=0;Behavior on width{NumberAnimation{duration:500;easing.type:Easing.OutCubic}}}
        }
        MouseArea {x:10;y:90;width:210;height:45;hoverEnabled:true;ToolTip.visible:containsMouse && Number(root.system.temperature)<0;ToolTip.text:"Windows does not expose this temperature sensor."}
        Text {x:828;y:16;width:104;text:"Usage";font.family:"Rubik";font.pixelSize:12;color:root.theme.muted;horizontalAlignment:Text.AlignHCenter}
        Item {
            id:cpuBadge;x:832;y:36;width:96;height:96
            Shape {
                anchors.centerIn:parent;width:200;height:200;scale:cpuBadge.width/200
                preferredRendererType:Shape.CurveRenderer
                ShapePath {strokeWidth:-1;fillColor:Qt.alpha(root.theme.primary,0.13);PathSvg{path:typeof shapeCookie9!=="undefined" ? shapeCookie9.path:""}}
            }
            Text {anchors.centerIn:parent;text:Math.round(root.system.cpuPercent || 0)+"%";font.family:"Rubik";font.pixelSize:25;font.weight:Font.Medium;color:root.theme.primary}
        }
    }
    GlassWidget {
        x:0;y:160;width:355;height:220;radius:24;surfaceColor:root.moduleSurface;highlightColor:root.theme.foreground
        ArcGauge {x:25;y:24;width:124;height:124;value:root.system.storagePercent || 0;strokeColor:root.theme.secondary;trackColor:root.gaugeTrack;lineWidth:6;startAngle:-225;sweepAngle:270}
        Icon {x:72;y:49;width:30;height:24;name:"hard_drive";size:24;color:root.theme.secondary}
        Text {x:25;y:79;width:124;text:Math.round(root.system.storagePercent || 0)+"%";font.family:"Rubik";font.pixelSize:28;color:root.theme.secondary;horizontalAlignment:Text.AlignHCenter}
        Text {x:25;y:113;width:124;text:"Used";font.family:"Rubik";font.pixelSize:12;color:root.theme.muted;horizontalAlignment:Text.AlignHCenter}
        Text {x:169;y:55;text:"Storage";font.family:"Rubik";font.pixelSize:20;color:root.theme.foreground}
        Text {x:169;y:86;width:166;text:root.usage(root.system.storageUsed,root.system.storageTotal);font.family:"Rubik";font.pixelSize:16;color:root.theme.secondary;elide:Text.ElideRight}
        Rectangle {
            x:24;y:165;width:307;height:36;radius:12;color:Qt.alpha(root.theme.cardAlt,0.82);border.width:1;border.color:root.subtleEdge
            Icon {x:16;anchors.verticalCenter:parent.verticalCenter;name:"storage";size:18;color:root.theme.secondary}
            Text {x:43;anchors.verticalCenter:parent.verticalCenter;width:220;text:root.drive.label ? root.drive.name+" · "+root.drive.label : root.drive.name || "No drives";font.family:"Rubik";font.pixelSize:14;color:root.theme.secondary;elide:Text.ElideRight;horizontalAlignment:Text.AlignHCenter}
            Rectangle {x:267;y:8;width:1;height:parent.height-16;color:root.subtleEdge}
            Icon {x:276;anchors.verticalCenter:parent.verticalCenter;name:"expand_more";size:21;color:root.theme.secondary}
            MouseArea {anchors.fill:parent;cursorShape:Qt.PointingHandCursor;onClicked:driveMenu.open()}
            Menu {
                id:driveMenu;objectName:"storageDrives";y:39;width:307;padding:6;popupType:Popup.Window
                background:Rectangle {radius:14;color:root.theme.cardAlt;border.width:1;border.color:root.theme.outline}
                Repeater {model:root.system.drives || []
                    MenuItem {
                        id:driveItem;required property var modelData;text:modelData.name+(modelData.label ? " · "+modelData.label:"");checkable:true;checked:modelData.id===root.system.selectedDrive;implicitHeight:40;font.family:"Rubik";font.pixelSize:14
                        contentItem:Text {text:driveItem.text;font:driveItem.font;color:root.theme.foreground;verticalAlignment:Text.AlignVCenter;leftPadding:30;rightPadding:8;elide:Text.ElideRight}
                        indicator:Icon {x:10;anchors.verticalCenter:parent.verticalCenter;name:"check";size:18;color:root.theme.primary;visible:driveItem.checked}
                        background:Rectangle {radius:9;color:driveItem.highlighted ? Qt.alpha(root.theme.primary,0.15):"transparent"}
                        onTriggered:root.backend.selectDrive(modelData.id)
                    }
                }
            }
        }
    }
    GlassWidget {
        x:367;y:160;width:390;height:220;radius:24;surfaceColor:root.moduleSurface;highlightColor:root.theme.foreground
        Icon {x:20;y:18;name:"swap_vert";size:21;color:root.theme.secondary}
        Text {x:50;y:18;text:"Network";font.family:"Rubik";font.pixelSize:20;color:root.theme.foreground}
        Canvas {
            id:graph;x:24;y:61;width:342;height:49;antialiasing:true
            property var samples:root.system.networkHistory || []
            onSamplesChanged:requestPaint()
            onPaint:{const c=getContext("2d");c.reset();const a=samples,maximum=Math.max(1024,...a);if(a.length<2)return;const points=[];for(let i=0;i<a.length;i++)points.push({x:i/(a.length-1)*width,y:height-2-Math.min(1,a[i]/maximum)*(height-5)});c.beginPath();c.moveTo(0,height);for(let p of points)c.lineTo(p.x,p.y);c.lineTo(width,height);c.closePath();const shade=c.createLinearGradient(0,0,0,height);shade.addColorStop(0,Qt.alpha(root.theme.tertiary,0.20));shade.addColorStop(1,Qt.alpha(root.theme.tertiary,0.015));c.fillStyle=shade;c.fill();c.beginPath();for(let i=0;i<points.length;i++){const p=points[i];if(i===0)c.moveTo(p.x,p.y);else c.lineTo(p.x,p.y)}c.strokeStyle=Qt.alpha(root.theme.tertiary,0.88);c.lineWidth=1.7;c.lineJoin="round";c.stroke()}
            Connections {target:root;function onThemeChanged(){graph.requestPaint()}}
        }
        Repeater {
            model:[{glyph:"arrow_downward",label:"Download",value:root.bytes(root.system.downloadRate)+"/s"},{glyph:"arrow_upward",label:"Upload",value:root.bytes(root.system.uploadRate)+"/s"},{glyph:"swap_vert",label:"Total",value:root.bytes(root.system.downloadTotal)+" / "+root.bytes(root.system.uploadTotal)}]
            Item {required property int index;required property var modelData;x:22;y:122+index*28;width:346;height:24
                Icon {x:0;anchors.verticalCenter:parent.verticalCenter;name:parent.modelData.glyph;size:18;color:index===2 ? root.theme.secondary : root.theme.tertiary}
                Text {x:29;anchors.verticalCenter:parent.verticalCenter;text:parent.modelData.label;font.family:"Rubik";font.pixelSize:14;color:root.theme.muted}
                Text {x:108;anchors.verticalCenter:parent.verticalCenter;width:238;horizontalAlignment:Text.AlignRight;text:parent.modelData.value;font.family:"Rubik";font.pixelSize:index===2 ? 12:15;font.weight:index===2 ? Font.Normal:Font.Medium;color:index===2 ? root.theme.muted:root.theme.tertiary}
            }
        }
    }
    GlassWidget {
        x:769;y:160;width:181;height:220;radius:14;surfaceColor:root.moduleSurface;highlightColor:root.theme.foreground
        Icon {x:22;y:18;name:"memory_alt";size:21;color:root.theme.tertiary}
        Text {x:52;y:19;text:"Memory";font.family:"Rubik";font.pixelSize:18;color:root.theme.foreground}
        ArcGauge {x:35;y:62;width:111;height:111;value:root.system.memoryPercent || 0;strokeColor:root.theme.tertiary;trackColor:root.gaugeTrack;lineWidth:6;startAngle:-225;sweepAngle:270}
        Text {x:35;y:98;width:111;horizontalAlignment:Text.AlignHCenter;text:Math.round(root.system.memoryPercent || 0)+"%";font.family:"Rubik";font.pixelSize:24;color:root.theme.tertiary}
        Text {x:35;y:128;width:111;horizontalAlignment:Text.AlignHCenter;text:"Used";font.family:"Rubik";font.pixelSize:12;color:root.theme.muted}
        Text {x:8;y:185;width:165;horizontalAlignment:Text.AlignHCenter;text:root.usage(root.system.memoryUsed,root.system.memoryTotal);font.family:"Rubik";font.pixelSize:13;color:root.theme.foreground}
    }
    Rectangle {
        id:batteryTank
        readonly property real level:root.system.batteryAvailable ? Math.max(0,Math.min(100,Number(root.system.batteryPercent || 0))) : 0
        property real animatedLevel:level
        Behavior on animatedLevel{NumberAnimation{duration:500;easing.type:Easing.OutCubic}}
        x:962;y:0;width:150;height:380;radius:16;color:Qt.tint(root.moduleSurface,Qt.alpha(root.theme.primary,0.09));clip:true
        Item {
            x:1;y:1;width:parent.width-2;height:Math.max(0,batteryFill.y-1);clip:true
            BatteryContents {x:-1;y:-1;width:batteryTank.width;height:batteryTank.height;accentColor:root.theme.primary;textColor:root.theme.foreground;subTextColor:root.theme.muted}
        }
        Rectangle {
            id:batteryFill;x:1;width:parent.width-2;height:root.system.batteryAvailable ? (parent.height-2)*batteryTank.animatedLevel/100 : 0;y:parent.height-1-height;radius:15;topLeftRadius:4;topRightRadius:4;color:Qt.tint(root.theme.primary,Qt.alpha(root.theme.card,0.08));clip:true
            BatteryContents {x:-batteryFill.x;y:-batteryFill.y;width:batteryTank.width;height:batteryTank.height;accentColor:root.theme.onPrimary;textColor:root.theme.onPrimary;subTextColor:Qt.alpha(root.theme.onPrimary,0.8)}
        }
        Rectangle {anchors.fill:parent;radius:parent.radius;color:"transparent";border.width:1;border.color:Qt.alpha(root.theme.primary,0.20)}
    }
    component BatteryContents:Item {
        property color accentColor
        property color textColor
        property color subTextColor
        id:batteryContents
        Icon {x:16;y:16;name:"battery_full";size:23;color:parent.accentColor}
        Text {x:16;y:47;text:"Battery";font.family:"Rubik";font.pixelSize:16;color:parent.textColor}
        Text {anchors.right:parent.right;anchors.rightMargin:16;anchors.bottom:percentageRow.top;anchors.bottomMargin:6;text:root.system.batteryAvailable ? (root.system.batteryCharging ? "Charging" : Number(root.system.batteryPercent)>=99 ? "Full":"Discharging") : "No battery";font.family:"Rubik";font.pixelSize:12;color:parent.subTextColor}
        Row {
            id:percentageRow;anchors.right:parent.right;anchors.bottom:parent.bottom;anchors.margins:16;spacing:4
            Icon {anchors.verticalCenter:parent.verticalCenter;name:"bolt";size:23;color:batteryContents.accentColor;visible:root.system.batteryAvailable && root.system.batteryCharging || false}
            Text {text:root.system.batteryAvailable ? Math.round(root.system.batteryPercent || 0)+"%":"—";font.family:"Rubik";font.pixelSize:32;font.weight:Font.Medium;color:batteryContents.accentColor}
        }
    }
}
