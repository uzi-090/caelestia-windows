import QtQuick
import QtQuick.Controls
import ".."

Item {
    id:root
    property var backend
    property var theme:({card:"#29282d",cardAlt:"#39373f",foreground:"#e8e3ed",muted:"#bdb8c6",primary:"#cec4ff",secondary:"#c5c5e0",tertiary:"#e7b7d3",outline:"#4f4b58",onPrimary:"#302650"})
    property real unit:1
    readonly property var weather:backend && backend.data ? backend.data.weather || {} : ({})
    readonly property var days:weather.days && weather.days.length ? weather.days : Array.from({length:7},(_,i)=>{const d=new Date();d.setDate(d.getDate()+i);return {day:i===0 ? "Today":Qt.formatDate(d,"ddd"),date:Qt.formatDate(d,"MMM d"),icon:"cloud",min:null,max:null}})
    property date now:new Date()
    signal navigateRequested(int page)
    implicitWidth:720
    implicitHeight:400
    function temperature(n){return n!==undefined && n!==null && isFinite(n) ? Math.round(Number(n))+"°":"—"}
    Timer {interval:60000;running:true;repeat:true;onTriggered:root.now=new Date()}

    Text {x:14;y:0;width:400;text:root.weather.city || "Weather";font.family:"Rubik";font.pixelSize:28;font.weight:Font.DemiBold;color:root.theme.foreground;elide:Text.ElideRight}
    Text {x:14;y:36;width:400;text:Qt.formatDate(root.now,"dddd, MMMM d");font.family:"Rubik";font.pixelSize:12;color:root.theme.muted}
    Row {
        x:448;y:5;spacing:18
        WeatherStat {glyph:"wb_twilight";label:"Sunrise";value:root.weather.sunrise || "—"}
        WeatherStat {glyph:"bedtime";label:"Sunset";value:root.weather.sunset || "—"}
    }
    GlassWidget {
        x:0;y:62;width:720;height:110;radius:36;surfaceColor:root.theme.card;highlightColor:root.theme.foreground
        Row {
            anchors.centerIn:parent;spacing:22
            Icon {anchors.verticalCenter:parent.verticalCenter;width:84;height:84;name:root.weather.icon || "partly_cloudy_day";size:84;color:root.theme.secondary}
            Column {
                anchors.verticalCenter:parent.verticalCenter;spacing:0
                Text {text:root.weather.available ? root.temperature(root.weather.temperature)+"C":"—°C";font.family:"Rubik";font.pixelSize:56;font.weight:Font.Medium;color:root.theme.primary}
                Text {leftPadding:3;text:root.weather.condition || (root.weather.error ? "Weather unavailable":"Loading weather");font.family:"Rubik";font.pixelSize:15;color:root.theme.muted}
            }
        }
        MouseArea {anchors.fill:parent;hoverEnabled:true;ToolTip.visible:containsMouse && !!root.weather.stale;ToolTip.text:"Showing the last available forecast."}
    }
    Row {
        x:0;y:184;spacing:12
        DetailCard {glyph:"water_drop";label:"Humidity";value:root.weather.available ? Math.round(root.weather.humidity)+"%":"—";accent:root.theme.secondary}
        DetailCard {glyph:"thermostat";label:"Feels like";value:root.weather.available ? root.temperature(root.weather.feelsLike)+"C":"—";accent:root.theme.primary}
        DetailCard {glyph:"air";label:"Wind";value:root.weather.available ? Number(root.weather.windSpeed || 0).toFixed(1)+" km/h":"—";accent:root.theme.tertiary}
    }
    Text {x:10;y:247;text:"7-Day Forecast";font.family:"Rubik";font.pixelSize:16;font.weight:Font.Medium;color:root.theme.foreground}
    Row {
        x:0;y:282;spacing:9
        Repeater {
            model:root.days
            GlassWidget {
                id:forecast
                required property int index
                required property var modelData
                width:(720-6*9)/7;height:118;radius:16;surfaceColor:root.theme.card;highlightColor:root.theme.foreground;edgeAlpha:0.035
                Text {x:0;y:10;width:parent.width;text:forecast.index===0 ? "Today":forecast.modelData.day;font.family:"Rubik";font.pixelSize:16;font.weight:Font.Medium;color:root.theme.primary;horizontalAlignment:Text.AlignHCenter}
                Text {x:0;y:33;width:parent.width;text:forecast.modelData.date;font.family:"Rubik";font.pixelSize:12;color:root.theme.muted;horizontalAlignment:Text.AlignHCenter}
                Icon {anchors.horizontalCenter:parent.horizontalCenter;y:55;width:40;height:40;name:forecast.modelData.icon || "cloud";size:40;color:root.theme.secondary}
                Text {x:0;y:98;width:parent.width;text:root.temperature(forecast.modelData.min)+" / "+root.temperature(forecast.modelData.max);font.family:"Rubik";font.pixelSize:12;font.weight:Font.Medium;color:root.theme.tertiary;horizontalAlignment:Text.AlignHCenter}
                MouseArea {anchors.fill:parent;hoverEnabled:true;ToolTip.visible:containsMouse;ToolTip.text:forecast.modelData.condition || "Forecast unavailable"}
            }
        }
    }
    component WeatherStat: Item {
        property string glyph
        property string label
        property string value
        width:118;height:43
        Icon {x:0;y:7;name:parent.glyph;size:32;color:root.theme.tertiary}
        Text {x:40;y:2;text:parent.label;font.family:"Rubik";font.pixelSize:11;color:root.theme.muted}
        Text {x:40;y:20;text:parent.value;font.family:"Rubik";font.pixelSize:13;color:root.theme.foreground}
    }
    component DetailCard: GlassWidget {
        property string glyph
        property string label
        property string value
        property color accent
        width:232;height:48;radius:12;surfaceColor:root.theme.card;highlightColor:root.theme.foreground;edgeAlpha:0.035
        Row {anchors.centerIn:parent;spacing:10
            Icon {anchors.verticalCenter:parent.verticalCenter;name:parent.parent.glyph;size:23;color:parent.parent.accent}
            Column {spacing:1
                Text {text:parent.parent.parent.label;font.family:"Rubik";font.pixelSize:11;color:root.theme.muted}
                Text {text:parent.parent.parent.value;font.family:"Rubik";font.pixelSize:13;font.weight:Font.Medium;color:root.theme.foreground}
            }
        }
    }
}
