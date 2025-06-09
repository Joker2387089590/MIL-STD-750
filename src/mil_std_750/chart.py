from __future__ import annotations
import logging, math
from PySide6 import QtCharts
from PySide6.QtCore import Qt, QPointF

_log = logging.getLogger(__name__)
_min_Vce, _max_Vce = 10 ** -1.05, 10 ** 3.05
_min_Ic = 10e-6

class TestTrace(QtCharts.QLineSeries):
    def __init__(self, chart: Chart):
        super().__init__(chart)
        self.curren_point = QtCharts.QScatterSeries(self)
        self.setName('实测值')
        self.curren_point.setName('实测点')

    def add_test_point(self, Vce: float, Ic: float):
        chart = self.chart()
        if not isinstance(chart, Chart): return
        Ic = max(chart.ay.min(), Ic)
        Vce = max(chart.ax.min(), Vce)
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

        self.traces: list[TestTrace] = []
        self.trace: TestTrace | None = None

    def _add(self, series: QtCharts.QAbstractSeries):
        self.addSeries(series)
        series.attachAxis(self.ax)
        series.attachAxis(self.ay)

    def set_targets(self, targets: list[tuple[float, float]]):
        # filter invalid targets
        targets = [(v, i) for v, i in targets if v > 0 and i > 0]
        
        self.target.replace([QPointF(v, i) for v, i in targets])

        # adjust Y
        Ics = [i for v, i in targets]
        Ics.append(10e-3)
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
            self.removeSeries(trace.curren_point)
            self.removeSeries(trace)
            
        self.trace = None
