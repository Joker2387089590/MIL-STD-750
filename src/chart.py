from PySide6 import QtCore, QtGui, QtWidgets, QtCharts
from PySide6.QtCore import Qt

class Chart(QtCharts.QChart):
    def __init__(self):
        super().__init__()
        self.upper = QtCharts.QLineSeries(self)
        self.area = QtCharts.QAreaSeries(self.upper)
        self.area.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0x55, 0xAA)))
        self.scatter = QtCharts.QScatterSeries(self)
        self.addSeries(self.area)
        self.addSeries(self.upper)
        self.addSeries(self.scatter)
        self.createDefaultAxes()

    def set_points(self, points: list[tuple[float, float]]):
        points.sort(key=lambda p: p[0])
        self.axes(Qt.Orientation.Horizontal)[0].setRange(points[0][0], points[-1][0])

        qpoints = [QtCore.QPointF(x, y) for x, y in points]
        self.scatter.replace(qpoints)
        self.upper.replace(qpoints)

        Config = QtCharts.QXYSeries.PointConfiguration
        colors = [
            QtGui.QColor(0,    0xFF, 0, 0x80),
            QtGui.QColor(0xFF, 0,    0, 0x80),
        ]
        for i in range(len(points)):
            self.scatter.setPointConfiguration(i, {
                Config.Color: colors[i % len(colors)],
                Config.Size: 15.0
            })
    
    def set_y_range(self, min: float, max: float):
        self.axes(Qt.Orientation.Vertical)[0].setRange(min, max)

if __name__ == '__main__':
    app = QtWidgets.QApplication()

    w = QtWidgets.QMainWindow()
    
    chart = Chart()
    chart.set_points([(-100, -100), (-60, -60), (20, -20)])
    chart.set_y_range(-100, 20)

    view = QtCharts.QChartView(chart, w)
    view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    w.setCentralWidget(view)

    w.show()
    exit(app.exec())
