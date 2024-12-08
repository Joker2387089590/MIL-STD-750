import logging
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import QWidget, QDialog, QMessageBox
from ..types import *
from ..chart import Chart
from .args_ui import Ui_ArgumentPanel

_log = logging.getLogger(__name__)

class Target(QWidget):
    changed = Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.Vce = QtWidgets.QDoubleSpinBox(self)
        self.Vce.setRange(0, 300)
        self.Vce.editingFinished.connect(self.changed)
        layout.addWidget(self.Vce, 1)

        self.Ic = QtWidgets.QDoubleSpinBox(self)
        self.Ic.setRange(0, 10_000)
        self.Ic.editingFinished.connect(self.changed)
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

class ArgumentPanel(QDialog):
    def __init__(self, names: set[str], parent: QWidget = None):
        super().__init__(parent)

        self.ui = ui = Ui_ArgumentPanel()
        self.names = names
        self.targets: list[Target] = []
        self.chart = Chart()

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        ui.setupUi(self)

        ui.chartView.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        ui.chartView.setChart(self.chart)
        ui.btnAdd.clicked.connect(self.add_target)

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
        for target in self.targets: targets.append(target.read())
        _log.debug(f'{targets = }')
        return targets

    @Slot()
    def update_targets(self):
        self.chart.set_targets(self.get_targets())

    def save(self):
        return Argument(
            name=self.ui.name.text(),
            type='NPN' if self.ui.radioNPN.isChecked() else 'PNP',
            duration=self.ui.duration.value(),
            Vc_max=self.ui.maxVc.value(),
            Ve_max=self.ui.maxVe.value(),
            targets=[t.save() for t in self.targets],
        )

    def load(self, data: Argument):
        self.ui.name.setText(data.name)
        
        if data.type == 'NPN':
            self.ui.radioNPN.setChecked(True)
        else:
            self.ui.radioPNP.setChecked(True)
        
        for td in data.targets: self.load_target(td)
        self.update_targets()

        self.ui.maxVc.setValue(data.Vc_max)
        self.ui.maxVe.setValue(data.Ve_max)

    def accept(self):
        name = self.ui.name.text()
        if not name:
            QMessageBox.warning(self, '参数错误', '参数名称为空！')
            return
        if name in self.names:
            QMessageBox.warning(self, '参数错误', '参数名称重复，请使用其他参数名称')
            return
        return super().accept()
    
    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return): return
        return super().keyPressEvent(event)
