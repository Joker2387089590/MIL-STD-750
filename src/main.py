import sys
from PySide6 import QtCore, QtWidgets, QtCharts, QtAsyncio
from PySide6.QtCore import Slot, QThread, QMetaObject, Qt
from PySide6.QtSerialPort import QSerialPortInfo
from .context import Argument, Device, Context
from .main_ui import Ui_MainWindow

class Chart(QtCharts.QChart):
    def __init__(self):
        super().__init__()
        self.ax = QtCharts.QValueAxis()
        self.ay = QtCharts.QValueAxis()
        self.addAxis(self.ax, Qt.AlignmentFlag.AlignBottom)
        self.addAxis(self.ay, Qt.AlignmentFlag.AlignLeft)

        self.current_vb_trace: QtCharts.QLineSeries | None = None

    @Slot()
    def make_new_vb_trace(self, vb: float):
        line_vce_ic = QtCharts.QLineSeries(self)
        line_vce_ic.setName(f'Vb = {vb:.3f}V')
        line_vce_ic.setPointLabelsVisible(True)
        self.addSeries(line_vce_ic)
        line_vce_ic.attachAxis(self.ax)
        line_vce_ic.attachAxis(self.ay)
        self.current_vb_trace = line_vce_ic
    
    @Slot()
    def add_test_point(self, Vb: float, Vc: float, Vce: float, Ic: float):
        self.current_vb_trace.append(Vce, Ic)
        count = self.current_vb_trace.count()
        print(f'[{count}] Vb, Vc, Vce, Ic = {Vb}, {Vc}, {Vce}, {Ic}')

class AsyncThread(QThread):
    def run(self):
        async def nothing(): pass
        QtAsyncio.run(nothing(), keep_running=True, quit_qapp=False, debug=True)

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.device: Device | None = None
        self.io_thread = AsyncThread(self)
        self.setup_ui(Ui_MainWindow())
        QtCore.QTimer.singleShot(0, self.io_thread, self.io_thread.start)

    def setup_ui(self, ui: Ui_MainWindow):
        self.ui = ui
        ui.setupUi(self)

        self.update_serial_info()

        self.chart_vce_ic = Chart()
        ui.chartView.setChart(self.chart_vce_ic)

        ui.btnStart.clicked.connect(self.start_test)

        ui.btnConnect.clicked.connect(self.connects)
        ui.btnDisconnect.clicked.connect(self.disconnects)

        self.target_series: QtCharts.QLineSeries | None = None
        ui.Vce.editingFinished.connect(self.check_arguments)
        ui.ic.editingFinished.connect(self.check_arguments)
        ui.Pmax.editingFinished.connect(self.check_arguments)

        self.check_arguments()

    def check_arguments(self):
        if self.target_series:
            self.chart_vce_ic.removeSeries(self.target_series)
            self.target_series = None

        Vce = self.ui.Vce.value()
        Ic = self.ui.ic.value()
        Pmax = self.ui.Pmax.value()

        if Pmax > Vce * Ic:
            self.ui.Pmax.setStyleSheet('''
                QDoubleSpinBox { border: 1px solid red; }
            ''')
            return
        self.ui.Pmax.setStyleSheet('')

        Vce_mid = Pmax / Ic
        Ic_mid = Pmax / Vce

        self.target_series = QtCharts.QLineSeries(self.chart_vce_ic)
        self.target_series.append(0, Ic)
        self.target_series.append(Vce_mid, Ic)
        v = Vce_mid
        while v < Vce:
            self.target_series.append(v, Pmax / v)
            v += 0.01
        self.target_series.append(Vce, Ic_mid)
        self.target_series.append(Vce, 0)

        self.chart_vce_ic.addSeries(self.target_series)
        self.target_series.attachAxis(self.chart_vce_ic.ax)
        self.target_series.attachAxis(self.chart_vce_ic.ay)
        self.chart_vce_ic.ax.setRange(0, Vce * 1.1)
        self.chart_vce_ic.ay.setRange(0, Ic * 1.1)

    def update_serial_info(self):
        self.ui.port.clear()
        self.ports = QSerialPortInfo.availablePorts()
        self.ui.port.addItems([port.portName() for port in self.ports])

    def exec(self):
        if self.device is None: raise Exception('device is not connected')

    @Slot()
    def connects(self):
        info = self.ports[self.ui.port.currentIndex()]
        self.ui.btnConnect.setEnabled(False)
        self.ui.btnDisconnect.setEnabled(True)
        try:
            self.device = Device(
                resist=info, 
                dmm=self.ui.dmm.text(),
                power_vb=self.ui.powerVb.text(),
                power_vc=self.ui.powerVc.text()
            )
            self.device.moveToThread(self.io_thread)
        except Exception as e:
            print(e, file=sys.stderr)

    @Slot()
    def disconnects(self):
        self.device.disconnects()
        self.device = None
        self.ui.btnConnect.setDisabled(False)
        self.ui.btnDisconnect.setDisabled(True)

    @Slot()
    def start_test(self):
        arg = Argument(
            self.ui.Vce.value(),
            self.ui.ic.value(),
            self.ui.Pmax.value(),
            self.ui.maxVb.value(),
            self.ui.maxVc.value(),
        )
        context = Context(arg, self.device)
        self.ui.btnPause.clicked.connect(context.pause)
        self.ui.btnStop.clicked.connect(context.stop)
        context.vbStarted.connect(self.chart_vce_ic.make_new_vb_trace)
        context.pointTested.connect(self.chart_vce_ic.add_test_point)

        context.moveToThread(self.io_thread)
        QtCore.QTimer.singleShot(0, context, lambda: context.run())




if __name__ == '__main__':
    app = QtWidgets.QApplication()
    w = MainWindow()
    w.show()
    QtAsyncio.run()
