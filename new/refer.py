import logging, json
from PySide6 import QtGui, QtWidgets, QtCharts
from PySide6.QtCore import Signal, Slot, Qt
from .types import *
from .refer_ui import Ui_Refer

log = logging.getLogger(__name__)

class Chart(QtCharts.QChart):
    def __init__(self):
        super().__init__()
        self.ax = QtCharts.QLogValueAxis()
        self.ay = QtCharts.QLogValueAxis()
        self.ay.setLabelFormat('%.0gA')
        self.addAxis(self.ax, Qt.AlignmentFlag.AlignBottom)
        self.addAxis(self.ay, Qt.AlignmentFlag.AlignLeft)
        self.ax.setRange(0.1, 1000)

        self.target = QtCharts.QScatterSeries(self)
        self.target.setName('目标测试点')
        self._add(self.target)

        self.curren_point = QtCharts.QScatterSeries(self)
        self.curren_point.setName('实测点')
        self._add(self.curren_point)

        self.traces = []
        self.trace = None

    def _add(self, series: QtCharts.QAbstractSeries):
        self.addSeries(series)
        series.attachAxis(self.ax)
        series.attachAxis(self.ay)

    def restart(self):
        self.curren_point.clear()
        for trace in self.traces:
            self.removeSeries(trace)
        self.trace = None

    def set_targets(self, targets: list[tuple[float, float]]):
        self.target.clear()
        Ics = [10e-3]
        for Vce, Ic in targets:
            if Vce <= 0 or Ic <= 0: continue
            self.target.append(Vce, Ic)
            Ics.append(Ic)
        self.ay.setRange(5e-5, max(Ics) * 10)

    def make_new_trace(self):
        if self.trace:
            for marker in self.legend().markers(self.trace):
                marker.setVisible(False)
        self.trace = QtCharts.QLineSeries(self)
        self.trace.setName('测试值')
        self._add(self.trace)
        self.traces.append(self.trace)
    
    def add_test_point(self, Vce: float, Ic: float):
        if Ic < 1e-5: Ic = 1e-5
        if Vce < 1e-4: Vce = 1e-4
        self.curren_point.clear()
        self.curren_point.append(Vce, Ic)
        self.trace.append(Vce, Ic)

class Target(QtWidgets.QWidget):
    changed = Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.Vce = QtWidgets.QDoubleSpinBox(self)
        self.Vce.setRange(0, 300)
        self.Vce.valueChanged.connect(self.changed)
        layout.addWidget(self.Vce, 1)

        self.Ic = QtWidgets.QDoubleSpinBox(self)
        self.Ic.setRange(0, 10_000)
        self.Ic.valueChanged.connect(self.changed)
        layout.addWidget(self.Ic, 1)

        self.remove = QtWidgets.QToolButton(self)
        self.remove.setText('-')
        layout.addWidget(self.remove)

    def read(self):
        return self.Vce.value(), self.Ic.value() * 1e-3
    
    def save(self):
        return self.Vce.value(), self.Ic.value()
    
    def load(self, data: tuple[float, float]):
        v, i = data
        self.Vce.setValue(v)
        self.Ic.setValue(i)

class ReferPanel(QtWidgets.QScrollArea):
    startRequested = Signal()
    abortRequested = Signal()
    targetsUpdated = Signal(list) # list[tuple[Vce, Ic]]
    refersApplied = Signal(list)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)

        w = QtWidgets.QWidget(self)
        self.ui = ui = Ui_Refer()
        ui.setupUi(w)
        self.setWidget(w)

        self.chart = Chart()
        self.targets: list[Target] = []
        self.refers: list[ReferData] = []
        
        ui.chartView.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        ui.chartView.setChart(self.chart)

        def try_start():
            self.ui.btnStart.setDisabled(True)
            self.startRequested.emit()
        ui.btnStart.clicked.connect(try_start)
        ui.btnStop.clicked.connect(self.abortRequested.emit)
        
        ui.btnAdd.clicked.connect(self.add_target)

        ui.btnApply.clicked.connect(self.apply_refers)
        ui.btnExport.clicked.connect(self.export_refers)

        self.update_running_state(False)

    @Slot()
    def add_target(self):
        target = Target()
        target.changed.connect(self.update_targets)
        target.remove.clicked.connect(lambda: self.remove_target(target))
        self.ui.layoutTargets.addWidget(target)
        self.targets.append(target)
        return target

    def load_target(self, data: tuple[float, float]):
        target: Target = self.add_target()
        target.Vce.setValue(data[0])
        target.Ic.setValue(data[1])
    
    def remove_target(self, target: Target):
        if target in self.targets:
            self.targets.remove(target)
        target.deleteLater()
        self.update_targets()

    def get_targets(self):
        targets: list[tuple[float, float]] = []
        for target in self.targets:
            targets.append(target.read())
        log.debug(f'{targets = }')
        return targets

    @Slot()
    def update_targets(self):
        targets = self.get_targets()
        self.chart.set_targets(targets)
        self.targetsUpdated.emit(targets)

    @Slot()
    def restart(self):
        self.chart.restart()
        self.ui.table.setRowCount(0)
    
    @Slot()
    def update_running_state(self, running: bool):
        self.ui.btnStart.setDisabled(running)
        self.ui.wArguments.setDisabled(running)
        self.ui.btnStop.setEnabled(running)

    @Slot()
    def start_target(self, Vce: float, Ic: float):
        self.chart.make_new_trace()

    @Slot()
    def add_test_point(self, Vce: float, Ic: float):
        self.chart.add_test_point(Vce, Ic)
    
    @Slot()
    def add_refer(self, data: ReferData):
        tb = self.ui.table
        row = tb.rowCount()
        tb.insertRow(row)
        for i, d in enumerate(data.tuple()):
            tb.setItem(row, i, QtWidgets.QTableWidgetItem(d))
        self.refers.append(data)

    @Slot()
    def export_refers(self):
        file, ext = QtWidgets.QFileDialog.getSaveFileName(
            self, '保存参考数据', filter='参考文件(*.ref)'
        )
        if not file: return

        try:
            log.debug(f'导出参考数据到 {file}')
            refs = [r.dict() for r in self.refers]
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(refs, f, ensure_ascii=False, indent=4)
        except:
            log.exception('导出参考数据失败')

    @Slot()
    def apply_refers(self):
        self.refersApplied.emit([r.dict() for r in self.refers])

    def save(self):
        return dict(
            type='NPN' if self.ui.radioNPN.isChecked() else 'PNP',
            targets=[t.save() for t in self.targets],
            limits=(self.ui.maxVc.value(), self.ui.maxVe.value())
        )

    def load(self, data):
        if not isinstance(data, dict): data = {}
        
        type = data.get('type', 'NPN')
        if type == 'NPN':
            self.ui.radioNPN.setChecked(True)
        else:
            self.ui.radioPNP.setChecked(True)
        
        targets = data.get('targets', [])
        for td in targets: self.load_target(td)

        limits = data.get('limits', (20, 20))
        self.ui.maxVc.setValue(limits[0])
        self.ui.maxVe.setValue(limits[1])
