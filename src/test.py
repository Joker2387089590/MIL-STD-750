from dataclasses import astuple
from PySide6 import QtGui, QtWidgets, QtCharts
from PySide6.QtCore import Signal, Slot, Qt
from .context import Argument, NpnResult, PnpResult
from .test_ui import Ui_TestPanel

Vce_min = 0.010
Vce_max = 1000
Ic_min = 1e-5

def unit(vb: QtWidgets.QDoubleSpinBox, ub: QtWidgets.QComboBox, suffix):
    u = ub.currentText().removesuffix(suffix)
    units = {
        'u': 1e-6,
        'μ': 1e-6,
        'm': 1e-3,
        '': 1,
        'k': 1e3,
        'M': 1e6,
    }
    return vb.value() * units[u]

class Chart(QtCharts.QChart):
    def __init__(self):
        super().__init__()
        self.ax = QtCharts.QLogValueAxis()
        self.ay = QtCharts.QLogValueAxis()
        # self.ax.setLabelFormat('%.0gV')
        self.ay.setLabelFormat('%.0gA')
        self.addAxis(self.ax, Qt.AlignmentFlag.AlignBottom)
        self.addAxis(self.ay, Qt.AlignmentFlag.AlignLeft)

        self.trace: QtCharts.QLineSeries | None = None

        from PySide6.QtGui import QPen, QBrush, QColor
        self.curren_point = QtCharts.QScatterSeries(self)
        self.curren_point.setName('当前测试点') 
        self.curren_point.setColor('purple')
        self.curren_point.setPen(QPen(QBrush(QColor('purple')), 0.3))
        self.addSeries(self.curren_point)
        self.curren_point.attachAxis(self.ax)
        self.curren_point.attachAxis(self.ay)

    def make_new_trace(self):
        if self.trace:
            self.removeSeries(self.trace)
        line_vce_ic = QtCharts.QLineSeries(self)
        line_vce_ic.setName('测试值')

        self.addSeries(line_vce_ic)
        line_vce_ic.attachAxis(self.ax)
        line_vce_ic.attachAxis(self.ay)
        self.trace = line_vce_ic
    
    @Slot()
    def add_test_point(self, Vce: float, Ic: float):
        if Ic < 1e-5: Ic = 1e-5
        if Vce < 1e-4: Vce = 1e-4
        self.curren_point.clear()
        self.curren_point.append(Vce, Ic)
        self.trace.append(Vce, Ic)

class TestPanel(QtWidgets.QWidget):
    startRequested = Signal()
    pauseRequested = Signal()
    abortRequested = Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.chart_vce_ic = Chart()
        self.target_series: QtCharts.QLineSeries | None = None
        self.result_series: QtCharts.QLineSeries | None = None
        self.setup_ui(Ui_TestPanel())

    def setup_ui(self, ui: Ui_TestPanel):
        self.ui = ui

        ui.setupUi(self)
        ui.chartView.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        ui.chartView.setChart(self.chart_vce_ic)

        def try_start():
            self.ui.btnStart.setDisabled(True)
            self.startRequested.emit()

        ui.btnStart.clicked.connect(try_start)
        ui.btnStop.clicked.connect(self.abortRequested.emit)

        ui.Vce.editingFinished.connect(self.check_arguments)
        ui.ic.editingFinished.connect(self.check_arguments)
        ui.Pmax.editingFinished.connect(self.check_arguments)
        ui.unitIc.currentIndexChanged.connect(self.check_arguments)
        ui.unitPmax.currentIndexChanged.connect(self.check_arguments)

        self.check_arguments()

    @property
    def input_Ic(self):
        return unit(self.ui.ic, self.ui.unitIc, 'A')
    
    @property
    def input_Pmax(self):
        return unit(self.ui.Pmax, self.ui.unitPmax, 'W')

    @Slot()
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
        self.target_series.setName('目标值')
        self.target_series.append(0.001, Ic)
        self.target_series.append(Vce_mid, Ic)
        self.target_series.append(Vce, Ic_mid)
        self.target_series.append(Vce, 1e-5)

        self.chart_vce_ic.addSeries(self.target_series)
        self.target_series.attachAxis(self.chart_vce_ic.ax)
        self.target_series.attachAxis(self.chart_vce_ic.ay)
        self.chart_vce_ic.ax.setRange(0.1, 1000)
        self.chart_vce_ic.ay.setRange(5e-5, Ic * 10)

    def get_arguments(self):
        return Argument(
            type='NPN' if self.ui.radioNPN.isChecked() else 'PNP',
            Vce=self.ui.Vce.value(),
            Ic=self.input_Ic,
            Pmax=self.input_Pmax,
            hFE=self.ui.hFE.value(),
            Vc_max=self.ui.maxVc.value(),
            Ve_max=self.ui.maxVe.value(),
            # targets=[]
        )
    
    @Slot()
    def update_running_state(self, running: bool):
        self.ui.btnStart.setDisabled(running)
        self.ui.wArguments.setDisabled(running)
        self.ui.btnStop.setEnabled(running)

    def reset_chart(self):
        self.chart_vce_ic.make_new_trace()

    @Slot()
    def add_npn_results(self, Vce, Ic, results: NpnResult):

        table = self.ui.dataTable
        row = table.rowCount()
        table.insertRow(row)
        for data in enumerate(astuple(results)):
            ...
            

        # table.setItem()
    
    @Slot()
    def add_point(self, Vce: float, Ic: float):
        self.chart_vce_ic.add_test_point(Vce, Ic)

    def save(self):
        return dict(
            type='NPN' if self.ui.radioNPN.isChecked() else 'PNP',
            Vce=self.ui.Vce.value(),
            Ic=self.ui.ic.value(),
            unitIc=self.ui.unitIc.currentText(),
            Pmax=self.ui.Pmax.value(),
            unitPmax=self.ui.unitPmax.currentText(),
            hFE=self.ui.hFE.value(),
            Vc_max=self.ui.maxVc.value(),
            Ve_max=self.ui.maxVe.value(),
        )

    def load(self, data: dict):
        type = data.get('type', 'NPN')
        btn = self.ui.radioNPN if type == 'NPN' else self.ui.radioPNP
        btn.setChecked(True)

        self.ui.Vce.setValue(data.get('Vce', 1.0))
        self.ui.ic.setValue(data.get('Ic', 10.0))
        self.ui.unitIc.setCurrentText(data.get('unitIc', 'mA'))
        self.ui.Pmax.setValue(data.get('Pmax', 5.0))
        self.ui.unitPmax.setCurrentText(data.get('unitPmax', 'mW'))
        self.ui.hFE.setValue(data.get('hFE', 70))
        self.ui.maxVc.setValue(data.get('Vc_max', 20.0))
        self.ui.maxVe.setValue(data.get('Ve_max', 20.0))
        self.check_arguments()
