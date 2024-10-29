import sys, math, debugpy
from dataclasses import dataclass
from contextlib import ExitStack
from PySide6 import QtCore, QtGui, QtWidgets, QtCharts
from PySide6.QtCore import Signal, Slot, QThread, Qt
from PySide6.QtSerialPort import QSerialPortInfo
from .context import Argument, Device, Context
from .main_ui import Ui_MainWindow

class Chart(QtCharts.QChart):
    def __init__(self):
        super().__init__()
        self.ax = QtCharts.QLogValueAxis()
        self.ay = QtCharts.QLogValueAxis()
        self.ax.setLabelFormat('%gV')
        self.ay.setLabelFormat('%gA')
        self.addAxis(self.ax, Qt.AlignmentFlag.AlignBottom)
        self.addAxis(self.ay, Qt.AlignmentFlag.AlignLeft)
        self.trace: QtCharts.QLineSeries | None = None
        self.mapping: dict[tuple[float, float], tuple[float, float]] = {}

    def make_new_trace(self):
        if self.trace:
            self.removeSeries(self.trace)
        line_vce_ic = QtCharts.QLineSeries(self)
        line_vce_ic.hovered.connect(self.show_point_tooltip)

        self.addSeries(line_vce_ic)
        line_vce_ic.attachAxis(self.ax)
        line_vce_ic.attachAxis(self.ay)
        self.trace = line_vce_ic
        self.mapping = {}

    @Slot()
    def show_point_tooltip(self, point: QtCore.QPointF, state: bool):
        pass
    
    @Slot()
    def add_test_point(self, Vc: float, Ve: float, Vce: float, Ic: float):
        if Ic < 1e-4: Ic = 1e-4
        self.trace.append(Vce, Ic)
        self.mapping[(Vc, Ve)] = (Vce, Ic)

class DebugThread(QThread):
    def run(self):
        debugpy.debug_this_thread()
        return super().run()
    
class Devices(QtWidgets.QWidget):
    connectRequested = Signal(list[str])
    disconnectRequested = Signal(list[str])

    def __init__(self, parent = None, f = Qt.WindowType.Widget):
        super().__init__(parent, f)

        @dataclass
        class Panel:
            ip: QtWidgets.QLineEdit
            connects: QtWidgets.QPushButton
            disconnects: QtWidgets.QPushButton

        self.devices: dict[str, Panel] = {}

        devices = [
            ('Vce', '数字万用表 SDM4065A', '测量 V<sub>ce</sub>'),
            ('Vbe', '数字万用表 SDM4065A', '测量 V<sub>be</sub>'),
            ('Vcb', '数字万用表 SDM4065A', '测量 V<sub>cb</sub>'),
            ('Ic',  '数字万用表 SDM4065A', '测量 I<sub>c</sub>'),
            ('Ie',  '数字万用表 SDM4065A', '测量 I<sub>e</sub>'),
            ('Vc',  '直流电源 IT-M3900D',  '输出 V<sub>c</sub>'),
            ('Ve',  '直流电源 IT-M3900D',  '输出 V<sub>e</sub>'),
        ]
        vlayout = QtWidgets.QVBoxLayout(self)
        for key, model, name in devices:
            w = QtWidgets.QWidget(self)
            vlayout.addWidget(w)

            layout = QtWidgets.QFormLayout(w)

            ip = QtWidgets.QLineEdit(parent=w)
            xmodel = QtWidgets.QLabel(model, w)
            xmodel.setTextFormat(Qt.TextFormat.RichText)
            connects = QtWidgets.QPushButton('连接', parent=w)
            disconnects = QtWidgets.QPushButton('断开', parent=w)

            disconnects.setEnabled(False)

            connects.clicked.connect(lambda: self._try_connect(key))
            disconnects.clicked.connect(lambda: self._try_disconnect(key))

            xlayout = QtWidgets.QHBoxLayout()
            xlayout.addWidget(xmodel)
            xlayout.addWidget(connects)
            xlayout.addWidget(disconnects)

            layout.addRow(xlayout)
            layout.addRow('设备功能', QtWidgets.QLabel(name, w))
            layout.addRow('IP 地址', ip)
            layout.setHorizontalSpacing(150)

            self.devices[key] = Panel(
                ip=ip,
                connects=connects,
                disconnects=disconnects
            )

        layout_all = QtWidgets.QHBoxLayout()
        connects_all = QtWidgets.QPushButton(self)
        disconnects_all = QtWidgets.QPushButton(self)

        layout_all.addStretch(1)
        layout_all.addWidget(connects_all)
        layout_all.addWidget(disconnects_all)

        vlayout.addLayout(layout_all)
        vlayout.addStretch(1)

    def _try_connect(self, key):
        panel = self.get_panel(key)
        panel.connects.setEnabled(False)
        self.connectRequested.emit(key)

    def _try_disconnect(self, key):
        panel = self.get_panel(key)
        panel.disconnects.setEnabled(False)
        self.disconnectRequested.emit(key)

    def get_panel(self, key):
        return self.devices[key]
    
    def update_state(self, key, connected: bool):
        panel = self.get_panel(key)
        panel.connects.setDisabled(connected)
        panel.disconnects.setEnabled(connected)
        self.setEnabled(True)

    def save(self):
        ...

    def load(self, data):
        ...

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.device: Device | None = None
        self.io_thread = DebugThread(self)
        self.chart_vce_ic = Chart()
        self.target_series: QtCharts.QLineSeries | None = None
        self.setup_ui(Ui_MainWindow())
        self.io_thread.start()

    def setup_ui(self, ui: Ui_MainWindow):
        self.ui = ui

        ui.setupUi(self)
        ui.chartView.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        ui.chartView.setChart(self.chart_vce_ic)
        ui.wControl.setEnabled(False)

        ui.btnConnect.clicked.connect(self.connects)
        ui.btnDisconnect.clicked.connect(self.disconnects)
        ui.btnRefreshPort.clicked.connect(self.update_serial_info)

        ui.btnStart.clicked.connect(self.start_test)

        ui.Vce.editingFinished.connect(self.check_arguments)
        ui.ic.editingFinished.connect(self.check_arguments)
        ui.Pmax.editingFinished.connect(self.check_arguments)

        self.update_serial_info()
        self.check_arguments()

    @property
    def input_Ic(self):
        return self.ui.ic.value() * 1e-3 # mA => A
    
    @property
    def input_Pmax(self):
        return self.ui.Pmax.value() * 1e-3 # mW => W

    def check_arguments(self):
        if self.target_series:
            self.chart_vce_ic.removeSeries(self.target_series)
            self.target_series = None

        Vce = self.ui.Vce.value()
        Ic = self.input_Ic
        Pmax = self.input_Pmax

        if Pmax > Vce * Ic:
            self.ui.Pmax.setStyleSheet('''
                QDoubleSpinBox { border: 1px solid red; }
            ''')
            return
        self.ui.Pmax.setStyleSheet('')

        Vce_mid = Pmax / Ic
        Ic_mid = Pmax / Vce

        self.target_series = QtCharts.QLineSeries(self.chart_vce_ic)
        self.target_series.append(0.01, Ic)
        self.target_series.append(Vce_mid, Ic)
        self.target_series.append(Vce, Ic_mid)
        self.target_series.append(Vce, 1e-4)

        self.chart_vce_ic.addSeries(self.target_series)
        self.target_series.attachAxis(self.chart_vce_ic.ax)
        self.target_series.attachAxis(self.chart_vce_ic.ay)
        self.chart_vce_ic.ax.setRange(0.01, Vce * 10)
        self.chart_vce_ic.ay.setRange(1e-4, Ic * 10)

    def update_serial_info(self):
        old = self.ui.port.currentText()
        self.ui.port.clear()

        self.ports = QSerialPortInfo.availablePorts()
        if len(self.ports) == 0: return

        self.ui.port.addItems([port.portName() for port in self.ports])
        if old in self.ports:
            self.ui.port.setCurrentText(old)
        else:
            self.ui.port.setCurrentIndex(0)

    @Slot()
    def connects(self):
        try:
            with ExitStack() as stack:
                device = Device(
                    resist=self.ports[self.ui.port.currentIndex()], 
                    dmm=self.ui.dmm.text(),
                    power_vc=self.ui.powerVc.text(),
                    power_ve=self.ui.powerVe.text(),
                )
                device.moveToThread(self.io_thread)
                self.device = device
                def clean_devices():
                    self.device.disconnects()
                    del self.device
                stack.callback(clean_devices)

                self.set_connect_state(True)
                stack.callback(self.set_connect_state, False)

                self._disconnects = stack.pop_all()
        except Exception as e:
            print(e, file=sys.stderr)

    @Slot()
    def disconnects(self):
        self._disconnects.close()
    
    def set_connect_state(self, connected: bool):
        self.ui.btnConnect.setDisabled(connected)
        self.ui.btnDisconnect.setEnabled(connected)
        self.ui.wControl.setEnabled(connected)
        self.ui.wDevices.setDisabled(connected)

    @Slot()
    def start_test(self):
        arg = Argument(
            Vce=self.ui.Vce.value(),
            Ic=self.input_Ic,
            Pmax=self.input_Pmax,
            hFE=self.ui.hFE.value(),
            Vc_max=self.ui.maxVc.value(),
            Ve_max=self.ui.maxVe.value(),
        )
        context = Context(arg, self.device)
        self.ui.btnPause.clicked.connect(context.pause)
        self.ui.btnStop.clicked.connect(context.stop)
        context.stopped.connect(self.finish_test)

        self.chart_vce_ic.make_new_trace()
        context.pointTested.connect(self.chart_vce_ic.add_test_point)

        self.ui.wConnect.setDisabled(True)
        self.ui.btnStart.setEnabled(False)
        self.ui.btnPause.setEnabled(True)
        self.ui.btnStop.setEnabled(True)

        context.moveToThread(self.io_thread)
        QtCore.QTimer.singleShot(0, context, context.run)
    
    @Slot()
    def finish_test(self):
        self.ui.wConnect.setDisabled(False)
        self.ui.btnStart.setEnabled(True)
        self.ui.btnPause.setEnabled(False)
        self.ui.btnStop.setEnabled(False)

if __name__ == '__main__':
    app = QtWidgets.QApplication()
    w = MainWindow()
    w.show()
    exit(app.exec())

