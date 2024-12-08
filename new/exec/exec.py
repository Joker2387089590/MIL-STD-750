import logging
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Signal, Slot
from ..types import *
from ..chart import Chart
from .exec_ui import Ui_ExecPanel

_log = logging.getLogger(__name__)

class ExecPanel(QtWidgets.QWidget):
    startRequested = Signal()
    abortRequested = Signal()

    def __init__(self, parent = None):
        super().__init__(parent)
        self.ui = ui = Ui_ExecPanel()
        ui.setupUi(self)

        def try_start():
            self.ui.btnStart.setDisabled(True)
            self.startRequested.emit()
        ui.btnStart.clicked.connect(try_start)
        ui.btnStop.clicked.connect(self.abortRequested.emit)

        self.chart = Chart()
        ui.chartView.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        ui.chartView.setChart(self.chart)

        self.trace = None
        self.refers: list[ReferResult] = []

    @Slot()
    def update_running_state(self, running: bool):
        self.ui.btnStart.setDisabled(running)
        self.ui.btnStop.setEnabled(running)

    def set_current_refer(self):
        ...

    def get_arguments(self) -> ExecArgument:
        ...

    def save(self):
        ...

    def load(self, data):
        ...

    def restart(self):
        self.chart.restart()

    def start_target(self):
        self.chart.make_trace()

    def add_test_point(self, Vce: float, Ic: float):
        self.chart.add_test_point(Vce, Ic)

    def add_refer(self, data: ReferResult):
        tb = self.ui.table
        row = tb.rowCount()
        tb.insertRow(row)
        for i, d in enumerate(data.tuple()):
            tb.setItem(row, i, QtWidgets.QTableWidgetItem(d))
        self.refers.append(data)

    def take_refers(self) -> list[ReferResult]:
        refers, self.refers = self.refers, []
        return refers
