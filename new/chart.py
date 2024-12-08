from __future__ import annotations
import logging, math
from PySide6 import QtCharts
from PySide6.QtCore import Qt

_log = logging.getLogger(__name__)
_min_Vce, _max_Vce = 10 ** -1.05, 10 ** 3.05
_min_Ic = 10e-3

class TestTrace(QtCharts.QLineSeries):
    def __init__(self, chart: Chart):
        super().__init__(chart)
        self.curren_point = QtCharts.QScatterSeries(self)
        self.setName('实测值')
        self.curren_point.setName('实测点')

    def add_test_point(self, Vce: float, Ic: float):
        Ic = max(_min_Ic, Ic)
        Vce = max(_min_Vce, Vce)
        self.curren_point.clear()
        self.curren_point.append(Vce, Ic)
        self.append(Vce, Ic)

class Chart(QtCharts.QChart):
    def __init__(self):
        super().__init__()
        self.setTitle('Vce-Ic关系图')

        self.ax = QtCharts.QLogValueAxis()
        self.ax.setRange(_min_Vce, _max_Vce)
        self.addAxis(self.ax, Qt.AlignmentFlag.AlignBottom)

        self.ay = QtCharts.QLogValueAxis()
        self.ay.setLabelFormat('%.0gA')
        self.ay.setRange(_min_Ic, 1.2)
        self.addAxis(self.ay, Qt.AlignmentFlag.AlignLeft)

        for axis in [self.ax, self.ay]:
            axis.setMinorTickCount(4)
            axis.setMinorGridLineVisible(True)

            mpen = axis.minorGridLinePen()
            mpen.setWidth(1)
            mpen.setStyle(Qt.PenStyle.DotLine)
            mpen.setDashPattern([pattern * 3 for pattern in mpen.dashPattern()])
            axis.setMinorGridLinePen(mpen)

            axis.setLinePenColor(Qt.GlobalColor.black)
            axis.setGridLineColor(Qt.GlobalColor.gray)
            axis.setMinorGridLineColor(Qt.GlobalColor.lightGray)

        self.target = QtCharts.QScatterSeries(self)
        self.target.setName('目标测试点')
        self._add(self.target)

        self.traces = []
        self.trace: TestTrace | None = None

    def _add(self, series: QtCharts.QAbstractSeries):
        self.addSeries(series)
        series.attachAxis(self.ax)
        series.attachAxis(self.ay)

    def set_targets(self, targets: list[tuple[float, float]]):
        self.target.clear()
        Ics = [10e-3]
        for Vce, Ic in targets:
            if Vce <= 0 or Ic <= 0: continue
            self.target.append(Vce, Ic)
            Ics.append(Ic)
        max_Ic = max(Ics)
        top_Ic = 10 ** (math.ceil(math.log10(max_Ic)) + 0.2)
        self.ay.setRange(5e-5, top_Ic)

    def make_trace(self):
        if self.trace:
            for marker in self.legend().markers(self.trace):
                marker.setVisible(False)

        self.trace = trace = TestTrace(self)
        self._add(trace)
        self._add(trace.curren_point)
        self.traces.append(trace)
        return trace
    
    def add_test_point(self, Vce: float, Ic: float):
        if not self.trace: 
            _log.error('no trace')
            return
        self.trace.add_test_point(Vce, Ic)

    def restart(self):
        for trace in self.traces:
            self.removeSeries(trace)
        self.trace = None
