import logging, math
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import QWidget, QDialog, QMessageBox
from ..types import *
from ..chart import Chart
from ..resist import values
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

        Rs = ['0', '1', '10', '100', '1k', '10k', '100k']

        self.Rc = QtWidgets.QComboBox(self)
        self.Rc.addItems(Rs)
        self.Rc.activated.connect(self.changed)
        layout.addWidget(self.Rc, 1)
        
        self.Re = QtWidgets.QComboBox(self)
        self.Re.addItems(Rs)
        self.Re.activated.connect(self.changed)
        layout.addWidget(self.Re, 1)

        self.Rx = QtWidgets.QLabel(self)
        self.Ic.valueChanged.connect(self.update_rx)
        layout.addWidget(self.Rx, 1)
        
        self.remove = QtWidgets.QToolButton(self)
        self.remove.setText('-')
        self.remove.setFixedSize(30, 30)
        layout.addWidget(self.remove)

    def update_rx(self, ic: float):
        Vce = self.Vce.value()
        ic = self.Ic.value() * 1e-3
        if Vce <= 0 or ic <= 0: return

        if Vce < 15:
            minR, maxR = 1 / ic,  30 / ic
        else:
            minR, maxR = 3 / ic,  30 / ic

        exp = int(math.ceil(math.log10(minR)))
        value = int(10 ** exp) if exp >= 0 else 0
        rx = values.get(value, '')
        self.Rx.setText(rx)
    
    def save(self):
        return ReferTarget(
            self.Vce.value(), 
            self.Ic.value() * 1e-3,
            self.Rc.currentText(),
            self.Re.currentText(),
        )
    
    def load(self, data: ReferTarget):
        self.Vce.setValue(data.Vce)
        self.Ic.setValue(data.Ic * 1000)
        self.Rc.setCurrentText(data.Rc)
        self.Re.setCurrentText(data.Re)

class ArgumentPanel(QDialog):
    def __init__(self, names: set[str], parent: QWidget | None = None):
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
    
    def remove_target(self, target: Target):
        if target in self.targets:
            self.targets.remove(target)
        target.deleteLater()
        self.update_targets()

    def get_targets(self):
        targets: list[ReferTarget] = []
        for target in self.targets: 
            targets.append(target.save())
        _log.debug(f'{targets = }')
        return targets

    def load_target(self, data: ReferTarget):
        target: Target = self.add_target()
        target.load(data)

    @Slot()
    def update_targets(self):
        targets: list[tuple[float, float]] = []
        for target in self.targets:
            data = target.save()
            targets.append((data.Vce, data.Ic))
        self.chart.set_targets(targets)

    def save(self):
        return ReferArgument(
            name=self.ui.name.text(),
            type='NPN' if self.ui.radioNPN.isChecked() else 'PNP',
            duration=self.ui.duration.value(),
            stable_duration=self.ui.stableTime.value(),
            Vc_max=self.ui.maxVc.value(),
            Ve_max=self.ui.maxVe.value(),
            Vceo=self.ui.Vceo.value(),
            Vebo=self.ui.Vebo.value(),
            Vcbo=self.ui.Vcbo.value(),
            targets=[t.save() for t in self.targets],
        )

    def load(self, data: ReferArgument):
        self.ui.name.setText(data.name)
        self.ui.duration.setValue(data.duration)
        self.ui.stableTime.setValue(data.stable_duration)
        
        if data.type == 'NPN':
            self.ui.radioNPN.setChecked(True)
        else:
            self.ui.radioPNP.setChecked(True)
        
        for td in data.targets: self.load_target(td)
        self.update_targets()

        self.ui.maxVc.setValue(data.Vc_max)
        self.ui.maxVe.setValue(data.Ve_max)
        self.ui.Vceo.setValue(data.Vceo)
        self.ui.Vebo.setValue(data.Vebo)
        self.ui.Vcbo.setValue(data.Vcbo)

    def accept(self):
        name = self.ui.name.text()
        if not name:
            QMessageBox.warning(self, '参数错误', '参数名称为空！')
            return
        if name in self.names:
            QMessageBox.warning(self, '参数错误', '参数名称重复，请使用其他参数名称')
            return
        return super().accept()
    
    def reject(self):
        ret = QMessageBox.warning(
            self, '参数编辑', '是否放弃修改?', 
            QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.No)
        if ret == QMessageBox.StandardButton.Yes:
            return super().reject()
    
    def keyPressEvent(self, event: QtGui.QKeyEvent): # type: ignore
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return): return
        return super().keyPressEvent(event)
