"""Caelestia-inspired native Windows dashboard. Run with pythonw or the exe."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import logging
import math
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import (QAbstractNativeEventFilter, QObject, Property, QTimer,
                            Signal, Slot, QUrl, QRect, Qt, QMetaObject, qInstallMessageHandler, QtMsgType)
from PySide6.QtGui import QCursor, QFont, QFontDatabase, QIcon, QRegion
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from backend import Backend
from shape_geometry import cookie_geometry, background_shapes
from wallpaper import WallpaperService
from gaming import WindowsGameGuard

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CaelestiaWindows'
STATE.mkdir(exist_ok=True, parents=True)
LOG = logging.getLogger('caelestia')
SERVER = 'CaelestiaWindowsDashboard-v1'


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam == 0xCA31:
            self.controller.toggle()
            return True, 0
        return False, 0


class Controller(QObject):
    openedChanged = Signal()
    geometryChanged = Signal()
    tabRequested = Signal(int)
    pinChanged = Signal()
    gameBlockedChanged = Signal()

    def __init__(self, app, backend, screen, pin=False, testing=False):
        super().__init__()
        self.app, self.backend, self.screen = app, backend, screen
        self.root = None
        self._opened = False
        self._pinned = pin
        self._testing = testing
        self._awaiting_pointer_entry = False
        self._last_pointer = None
        self._last_area = None
        self._last_inside = False
        self._layout_displaced_pointer = False
        self._suppress_hover = False
        self._last_mask = None
        self._frame_times = []
        self._game_guard = WindowsGameGuard()
        self._game_blocked = False
        self._game_reason = ''
        self._last_game_check = 0.0
        self._geometry()
        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(10)
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start()
        self._hotkey = HotkeyFilter(self)
        app.installNativeEventFilter(self._hotkey)
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.hotkey_registered = False
        self._register_hotkey()
        screen.geometryChanged.connect(self._geometry)

    def _register_hotkey(self):
        self.hotkey_registered = bool(ctypes.windll.user32.RegisterHotKey(
            None, 0xCA31, 0x4000 | 0x0001 | 0x0002, ord('D')))
        if not self.hotkey_registered:
            LOG.warning('Ctrl+Alt+D is already registered; tray and hover remain available')

    def _unregister_hotkey(self):
        if self.hotkey_registered:
            ctypes.windll.user32.UnregisterHotKey(None, 0xCA31)
            self.hotkey_registered = False

    def _geometry(self, *unused):
        g = self.screen.geometry()
        # The full-desktop reference puts Media at about54% of screen width.
        # Apply the same compact scale to every page, including high-DPI screens.
        self._scale = min(g.width()/1920, (g.height()-28)/549, 1.4)
        self._scale = max(0.5, self._scale)
        self._ww = math.ceil((1112+32+80)*self._scale)
        self._wh = math.ceil((435+114+28)*self._scale)
        self._wx = g.x() + (g.width()-self._ww)//2
        self._wy = g.y()
        self.geometryChanged.emit()

    @Property(bool, notify=openedChanged)
    def opened(self): return self._opened

    @Property(bool, notify=pinChanged)
    def pinned(self): return self._pinned

    @Property(bool, notify=gameBlockedChanged)
    def gameBlocked(self): return self._game_blocked

    @Property(bool, constant=True)
    def testing(self): return self._testing

    @Property(float, notify=geometryChanged)
    def scaleFactor(self): return self._scale

    @Property(int, notify=geometryChanged)
    def windowWidth(self): return self._ww

    @Property(int, notify=geometryChanged)
    def windowHeight(self): return self._wh

    @Property(int, notify=geometryChanged)
    def windowX(self): return self._wx

    @Property(int, notify=geometryChanged)
    def windowY(self): return self._wy

    @Property(int, notify=geometryChanged)
    def screenWidth(self): return self.screen.geometry().width()

    @Property(int, notify=geometryChanged)
    def screenHeight(self): return self.screen.geometry().height()

    @Slot()
    def showPanel(self):
        if self._refresh_game_protection(force=True): return
        self._suppress_hover = False
        # A keyboard/tray reveal can wait for the pointer's first entry. Once
        # entered, every exit retracts immediately, without a grace timer.
        self._awaiting_pointer_entry = True
        self.set_open(True)
        if self.root:
            self.root.raise_()

    @Slot()
    def hidePanel(self):
        self._awaiting_pointer_entry = False
        self._layout_displaced_pointer = False
        self._suppress_hover = True
        self.set_open(False)

    @Slot()
    def toggle(self):
        self.hidePanel() if self._opened else self.showPanel()

    @Slot(bool)
    def setPinned(self, value):
        if self._pinned == value: return
        self._pinned = value
        if not value:
            self._awaiting_pointer_entry = False
            self._layout_displaced_pointer = False
        self.pinChanged.emit()
        if value: self.showPanel()

    def set_open(self, value):
        if self._opened == value: return
        self._opened = value
        if value: self.backend.setVisualiserActive(True)
        else: QTimer.singleShot(550, lambda: self.backend.setVisualiserActive(self._opened))
        self.openedChanged.emit()

    def _fullscreen(self):
        if not self.root: return False
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        if not hwnd or int(hwnd) == int(self.root.winId()): return False
        name = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, name, 256)
        if name.value in ('Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'): return False
        r = wintypes.RECT()
        if not u.GetWindowRect(hwnd, ctypes.byref(r)): return False
        ratio = self.screen.devicePixelRatio()
        g = self.screen.geometry()
        return (r.left <= g.left()*ratio and r.top <= g.top()*ratio and
                r.right >= (g.right()+1)*ratio and r.bottom >= (g.bottom()+1)*ratio)

    def _refresh_game_protection(self, force=False):
        now = time.monotonic()
        if not force and now-self._last_game_check<0.25:
            return self._game_blocked
        self._last_game_check = now
        own_hwnd = int(self.root.winId()) if self.root else 0
        reason = self._game_guard.block_reason(own_hwnd)
        if not reason and self._fullscreen(): reason = 'fullscreen'
        self._game_reason = reason
        blocked = bool(reason)
        if blocked != self._game_blocked:
            self._game_blocked = blocked
            if blocked:
                # Disable the slide behaviour before changing opened, so
                # returning quickly from a game cannot reveal a closing frame.
                self.gameBlockedChanged.emit()
                self._unregister_hotkey()
                self.hidePanel()
                self.backend.setVisualiserActive(False)
                for popup in self.app.allWindows():
                    if popup.isVisible() and (popup.flags() & Qt.WindowType.WindowType_Mask)==Qt.WindowType.Popup:
                        popup.close()
            else:
                # Leaving a game restores only the collapsed tool window.
                # A pointer parked at its top edge must leave and re-enter.
                self._suppress_hover = True
                self._awaiting_pointer_entry = False
                self._register_hotkey()
                self.gameBlockedChanged.emit()
            self.tick_timer.setInterval(250 if blocked else 10)
            LOG.info('Gaming protection %s%s', 'active: ' if blocked else 'released', reason)
        return blocked

    def tick(self):
        if not self.root: return
        if self._refresh_game_protection(): return
        p = QCursor.pos()
        g = self.screen.geometry()
        left = float(self.root.property('panelLeft') or 0)
        top = float(self.root.property('panelTop') or 0)
        width = float(self.root.property('panelWidth') or 0)
        height = float(self.root.property('panelHeight') or 0)
        busy = bool(self.root.property('animationBusy'))
        popups = [w for w in self.app.allWindows()
                  if w.isVisible() and (w.flags() & Qt.WindowType.WindowType_Mask) == Qt.WindowType.Popup]
        popup_inside = any(w.geometry().contains(p) for w in popups)
        # The top-edge activation corridor remains part of the panel while its
        # expressive opening curve briefly overshoots downwards.
        area = QRect(self._wx+math.floor(left),self._wy,
                     math.ceil(width),max(4,math.ceil(top+height)))
        shoulder = 24*self._scale
        shoulder_y = (p.y()-self._wy-top)/shoulder
        wing_extra = shoulder*(1-math.sqrt(shoulder_y))**2 if 0<=shoulder_y<=1 else 0
        wing_inside = (0<=shoulder_y<=1 and
                       self._wx+left-wing_extra<=p.x()<self._wx+left+width+wing_extra)
        hot = QRect(g.center().x()-int(width)//2, g.top(), int(width), 4)
        if self._suppress_hover and not hot.contains(p): self._suppress_hover = False
        inside = (area.contains(p) or wing_inside or popup_inside) if self._opened else hot.contains(p)
        pointer_moved = self._last_pointer is not None and p != self._last_pointer
        if (self._opened and not inside and not pointer_moved and self._last_inside
                and self._last_area is not None and area != self._last_area):
            # A tab can shrink beneath a stationary pointer. That isn't a
            # pointer departure; the next actual outward move dismisses it.
            self._layout_displaced_pointer = True
        if inside:
            self._awaiting_pointer_entry = False
            self._layout_displaced_pointer = False
            if self._opened or (not self._suppress_hover and not self._refresh_game_protection(force=True)):
                self.set_open(True)
        elif (self._opened and not self._pinned and not self._awaiting_pointer_entry
              and (pointer_moved or not self._layout_displaced_pointer)):
            for popup in popups: popup.close()
            self.set_open(False)
        self._last_pointer = p
        self._last_area = area
        self._last_inside = inside
        # Restrict hit-testing to the animated panel. All other desktop space
        # belongs to the user's existing apps, including when this is hidden.
        hotspot = QRect(int((self._ww-width)/2),0,int(width),4)
        region = QRegion(hotspot)
        if self._opened or busy:
            clipped_top = max(0,int(top))
            visible_height = max(0,min(self._wh,int(top+height)+2)-clipped_top)
            if visible_height:
                region |= QRegion(QRect(max(0,math.floor(left)),clipped_top,math.ceil(width),visible_height))
                # Only the top curve shoulders extend beyond the body. Their
                # material is drawn by the same frosted surface as the panel.
                wing_bottom = min(self._wh,math.ceil(top+shoulder))
                if wing_bottom>clipped_top:
                    region |= QRegion(QRect(max(0,math.floor(left-shoulder)),clipped_top,
                                            math.ceil(width+2*shoulder),wing_bottom-clipped_top))
        if region != self._last_mask:
            self.root.setMask(region)
            self._last_mask = region

    @Slot()
    def record_frame(self):
        self._frame_times.append(time.perf_counter())
        if len(self._frame_times)>4000: self._frame_times=self._frame_times[-3000:]

    def diagnostics(self):
        times=self._frame_times
        intervals=[(b-a)*1000 for a,b in zip(times,times[1:]) if 0.001<b-a<0.1]
        intervals.sort()
        return {'frames':len(times),'activeFrameIntervals':len(intervals),
                'medianFrameMs':intervals[len(intervals)//2] if intervals else None,
                'p95FrameMs':intervals[int(len(intervals)*.95)] if intervals else None,
                'opened':self._opened,'pinned':self._pinned,'scale':self._scale,
                'gamingBlocked':self._game_blocked,'gamingReason':self._game_reason,
                'windowVisible':bool(self.root and self.root.isVisible()),
                'hotkeyRegistered':self.hotkey_registered,
                'tab':self.root.property('currentTab') if self.root else None,
                'audioPeak':self.backend.audioPeak,'data':self.backend.data}

    def stop(self):
        self.tick_timer.stop()
        self._unregister_hotkey()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--show', action='store_true')
    parser.add_argument('--pin', action='store_true')
    parser.add_argument('--tab', type=int, default=0)
    parser.add_argument('--capture-dir', type=Path)
    parser.add_argument('--quit-after', type=float, default=0)
    parser.add_argument('--isolated', action='store_true')
    parser.add_argument('--windowed-test', action='store_true')
    args = parser.parse_args()
    qt_messages = []
    handlers=[logging.FileHandler(STATE/'dashboard.log',encoding='utf-8')]
    if sys.stderr is not None: handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s',handlers=handlers)
    def qt_message(kind, context, message):
        level = logging.ERROR if kind in (QtMsgType.QtCriticalMsg,QtMsgType.QtFatalMsg) else logging.WARNING
        if kind in (QtMsgType.QtDebugMsg,QtMsgType.QtInfoMsg): level=logging.DEBUG
        if level>=logging.WARNING: qt_messages.append(str(message))
        LOG.log(level,'Qt: %s',message)
    qInstallMessageHandler(qt_message)
    os.environ.setdefault('QSG_RHI_BACKEND','d3d11')
    app = QApplication(sys.argv)
    app.setApplicationName('Caelestia for Windows')
    app.setOrganizationName('CaelestiaWindows')
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(ROOT/'assets/logo.svg')))

    server = QLocalServer()
    if not args.isolated:
        client = QLocalSocket()
        client.connectToServer(SERVER)
        if client.waitForConnected(400):
            client.write(b'show\n');client.waitForBytesWritten(400);return 0
        QLocalServer.removeServer(SERVER)
        if not server.listen(SERVER): LOG.warning('Could not open local command socket')

    for font in (ROOT/'assets').glob('*.ttf'):
        if QFontDatabase.addApplicationFont(str(font))<0: LOG.warning('Could not load font %s',font.name)
    app.setFont(QFont('Rubik',10))
    backend = Backend()
    backend.setVisualiserActive(False)
    screen = app.primaryScreen()
    wall = WallpaperService(screen.geometry().width(),screen.geometry().height())
    controller = Controller(app,backend,screen,args.pin or bool(args.capture_dir),args.windowed_test)
    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    context.setContextProperty('controller',controller)
    context.setContextProperty('systemBackend',backend)
    context.setContextProperty('wallpaper',wall)
    context.setContextProperty('shapeCookie9',cookie_geometry(200,720,'cookie9'))
    context.setContextProperty('shapeCookie12',cookie_geometry(200,720,'cookie12'))
    context.setContextProperty('backgroundShapePaths',background_shapes(200))
    engine.load(QUrl.fromLocalFile(str(ROOT/'qml/Main.qml')))
    if not engine.rootObjects():
        LOG.error('Dashboard UI failed to load from %s',ROOT/'qml/Main.qml')
        backend.stop();controller.stop();return 1
    root = engine.rootObjects()[0]
    root.setProperty('validationCapture',bool(args.capture_dir))
    controller.root = root
    root.frameSwapped.connect(controller.record_frame)
    root.setProperty('currentTab',max(0,min(3,args.tab)))
    controller.tick()
    LOG.info('Ready: screen=%sx%s scale=%.3f Direct3D11',screen.geometry().width(),screen.geometry().height(),controller.scaleFactor)

    tray = QSystemTrayIcon(QIcon(str(ROOT/'assets/logo.svg')),app)
    tray.setToolTip('Caelestia · hover at the top middle · Ctrl+Alt+D')
    menu = QMenu()
    menu.addAction('Show / hide',controller.toggle)
    pin = menu.addAction('Keep open');pin.setCheckable(True);pin.setChecked(controller.pinned)
    pin.toggled.connect(controller.setPinned)
    controller.pinChanged.connect(lambda:pin.setChecked(controller.pinned))
    for i,name in enumerate(('Dashboard','Media','Performance','Weather')):
        menu.addAction(name,lambda checked=False,n=i:(controller.tabRequested.emit(n),controller.showPanel()))
    menu.addSeparator()
    menu.addAction('Refresh wallpaper and weather',lambda:(wall.refresh(),backend.refresh()))
    menu.addAction('Exit',app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason:controller.toggle() if reason==QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()

    def new_command():
        connection = server.nextPendingConnection()
        def ready():
            cmd = bytes(connection.readAll()).decode().strip()
            if cmd=='show':controller.showPanel()
            elif cmd=='hide':controller.hidePanel()
            elif cmd=='quit':app.quit()
            elif cmd=='status':
                connection.write(json.dumps(controller.diagnostics()).encode('utf-8'))
                connection.flush()
            elif cmd=='pin':controller.setPinned(True)
            elif cmd=='unpin':controller.setPinned(False)
            elif cmd.startswith('tab '):
                try:controller.tabRequested.emit(int(cmd.split()[1]));controller.showPanel()
                except (IndexError,ValueError):pass
            connection.disconnectFromServer()
        connection.readyRead.connect(ready)
        if connection.bytesAvailable():ready()
    server.newConnection.connect(new_command)

    if args.show or args.pin or args.capture_dir:QTimer.singleShot(100,controller.showPanel)
    if args.quit_after:QTimer.singleShot(int(args.quit_after*1000),app.quit)
    if args.capture_dir:
        args.capture_dir.mkdir(exist_ok=True,parents=True)
        validation={'pages':[],'menus':[],'errors':[],'graphicsApi':str(root.rendererInterface().graphicsApi())}
        def capture(n):
            actual_tab=int(root.property('currentTab'))
            if actual_tab!=n or bool(root.property('animationBusy')) or not controller.opened:
                validation['errors'].append('Page capture was interrupted or unsettled: '+str(n))
            image = root.grabWindow()
            dpr = root.devicePixelRatio()
            left = max(0,int((float(root.property('panelLeft'))-24)*dpr))
            image.copy(left,0,int((float(root.property('panelWidth'))+48)*dpr),int((float(root.property('panelHeight'))+6)*dpr)).save(str(args.capture_dir/f'{n:02d}-{("dashboard","media","performance","weather")[n]}.png'))
            LOG.info('Capture %s: image=%sx%s dpr=%.2f',n,image.width(),image.height(),dpr)
            validation['pages'].append({'tab':n,'actualTab':actual_tab,'width':float(root.property('panelWidth')),
                                        'height':float(root.property('panelHeight')),'imageNull':image.isNull()})
            (args.capture_dir/'live-data.json').write_text(json.dumps(backend.data,indent=2),encoding='utf-8')
        for n in range(4):
            QTimer.singleShot(3500+n*1800,lambda n=n:controller.tabRequested.emit(n))
            QTimer.singleShot(4700+n*1800,lambda n=n:capture(n))
        def open_menu(name):
            menu_object=root.findChild(QObject,name)
            if menu_object is None:
                validation['errors'].append('Missing menu '+name)
                return
            QMetaObject.invokeMethod(menu_object,'open',Qt.ConnectionType.DirectConnection)
        def inspect_menu(name):
            menu_object=root.findChild(QObject,name)
            popups=[w for w in app.allWindows() if w.isVisible()
                    and (w.flags() & Qt.WindowType.WindowType_Mask)==Qt.WindowType.Popup]
            record={'name':name,'visible':bool(menu_object and menu_object.property('visible')),
                    'itemCount':int(menu_object.property('count') or 0) if menu_object else 0,
                    'popupWindowCount':len(popups),'windows':[]}
            for i,popup in enumerate(popups):
                g=popup.geometry()
                record['windows'].append({'x':g.x(),'y':g.y(),'width':g.width(),'height':g.height()})
                if hasattr(popup,'grabWindow'):
                    popup.grabWindow().save(str(args.capture_dir/f'{name}-{i}.png'))
            validation['menus'].append(record)
            if not record['visible'] or not popups:
                validation['errors'].append('Menu did not create an independent popup window: '+name)
            if menu_object:QMetaObject.invokeMethod(menu_object,'close',Qt.ConnectionType.DirectConnection)
        def finish_validation():
            validation['qtWarnings']=qt_messages
            validation['timing']=controller.diagnostics()
            validation['passed']=(len(validation['pages'])==4 and len(validation['menus'])==3
                                  and not validation['errors'] and not qt_messages
                                  and not any(page['imageNull'] for page in validation['pages']))
            (args.capture_dir/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
            LOG.info('Render and popup validation passed=%s',validation['passed'])
            app.quit()
        QTimer.singleShot(10600,lambda:controller.tabRequested.emit(1))
        QTimer.singleShot(11300,lambda:open_menu('mediaSessions'))
        QTimer.singleShot(11700,lambda:inspect_menu('mediaSessions'))
        QTimer.singleShot(12000,lambda:open_menu('mediaOptions'))
        QTimer.singleShot(12400,lambda:inspect_menu('mediaOptions'))
        QTimer.singleShot(12700,lambda:controller.tabRequested.emit(2))
        QTimer.singleShot(13400,lambda:open_menu('storageDrives'))
        QTimer.singleShot(13800,lambda:inspect_menu('storageDrives'))
        QTimer.singleShot(14200,finish_validation)
    app.aboutToQuit.connect(backend.stop)
    app.aboutToQuit.connect(controller.stop)
    return app.exec()


if __name__=='__main__':
    sys.exit(main())
