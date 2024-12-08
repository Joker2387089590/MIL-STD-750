import logging, json, math, ctypes
from PySide6 import QtCore, QtGui, QtWidgets, QtCharts
from PySide6.QtCore import Signal, Slot, Qt, QEvent
from PySide6.QtWidgets import (
    QGraphicsLinearLayout, QGraphicsScene, QGraphicsWidget, 
    QListWidgetItem,
    QMessageBox)
from ..types import *
from ..args import ArgumentPanel
from ..chart import Chart
from .refer_ui import Ui_ReferPanel

_log = logging.getLogger(__name__)

def _to_item(item_id: int) -> QListWidgetItem:
    return ctypes.cast(item_id, QListWidgetItem)

class ReferPanel(QtWidgets.QWidget):
    startRequested = Signal()
    abortRequested = Signal()
    refersApplied = Signal(list)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = ui = Ui_ReferPanel()
        self.refers: list[ReferData] = []

        ui.setupUi(self)
        self._setup_charts()
        self._setup_args()

        def try_start():
            self.ui.btnStart.setDisabled(True)
            self.startRequested.emit()
        ui.btnStart.clicked.connect(try_start)
        ui.btnStop.clicked.connect(self.abortRequested.emit)

        self.update_running_state(False)

    def _setup_charts(self):
        self.ui.chart.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        self.ui.chart.installEventFilter(self)

        self.scene = QGraphicsScene(self)
        self.ui.chart.setScene(self.scene)

        self.form = form = QGraphicsWidget()
        self.scene.addItem(form)

        layout = QGraphicsLinearLayout(Qt.Orientation.Vertical, form)
        layout.setSpacing(0)
        form.setLayout(layout)

        self.chart = Chart()
        expanding = QtWidgets.QSizePolicy.Policy.Expanding
        self.chart.setSizePolicy(expanding, expanding)
        layout.addItem(self.chart)

        self.trace = None

    def _setup_args(self):
        self.args: dict[int, Argument] = {}

        self.ui.listArgs.itemClicked.connect(self._set_current_args)
        self.ui.btnAddArg.clicked.connect(self._try_add_args)

        self.ui.listArgs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listArgs.customContextMenuRequested.connect(self._show_context_menu)

    def eventFilter(self, watched, event):
        if watched is self.ui.chart and event.type() == QEvent.Type.Resize:
            assert isinstance(event, QtGui.QResizeEvent)
            size = self.ui.chart.maximumViewportSize()
            self.form.resize(size)
            self.scene.setSceneRect(QtCore.QRect(QtCore.QPoint(), size))
        return super().eventFilter(watched, event)
    
    @property
    def current_item(self):
        return self.ui.listArgs.currentItem()

    def _set_current_args(self, item: QListWidgetItem):
        self.ui.listArgs.setCurrentItem(item)
        arg = self.args[id(item)]
        self.chart.set_targets(arg.targets)

    def _try_add_args(self):
        names = {_to_item(item).text() for item, _ in self.args.items()}
        panel = ArgumentPanel(names, self)
        def accept():
            arg = panel.save()
            item = QListWidgetItem(arg.name)
            self.ui.listArgs.addItem(item)
            self.args[id(item)] = arg
        panel.accepted.connect(accept)
        panel.open()

    def _show_context_menu(self, point: QtCore.QPoint):
        item = self.ui.listArgs.itemAt(point)
        if not item: return
        menu = QtWidgets.QMenu(self)
        menu.addAction('编辑', lambda: self._try_edit(item))
        menu.addAction('删除', lambda: self._try_delete(item))
        menu.exec(self.ui.listArgs.mapToGlobal(point))

    def _try_edit(self, item: QListWidgetItem):
        xid = id(item)
        args = self.args.pop(xid, None)
        if args is None: return
        names = {_to_item(i).text() for i, _ in self.args.items()}
        panel = ArgumentPanel(names, self)

        def accept(): self.args[xid] = panel.save()
        def reject(): self.args[xid] = args

        panel.accepted.connect(accept)
        panel.rejected.connect(reject)
        panel.load(args)
        panel.open()

    def _try_delete(self, item: QListWidgetItem):
        ret = QMessageBox.warning(
            self, '删除参数', f'是否删除 {item.text()}?', 
            QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes: return

        del self.args[id(item)]
        self.ui.listArgs.takeItem(self.ui.listArgs.row(item))

    @Slot()
    def restart(self):
        self.chart.restart()
        self.ui.table.setRowCount(0)
    
    @Slot()
    def update_running_state(self, running: bool):
        self.ui.btnStart.setDisabled(running)
        self.ui.btnStop.setEnabled(running)

    def get_arguments(self):
        return self.args[id(self.current_item)]
    
    def save(self):
        current = self.ui.listArgs.row(self.current_item)
        items = []
        for row in range(self.ui.listArgs.count()):
            item = self.ui.listArgs.item(row)
            arg = self.args[id(item)]
            items.append(asdict(arg))
        return dict(
            current=current,
            items=items,
        )
    
    def load(self, data: dict):
        for d in data.get('items', []):
            arg = Argument(**d)
            item = QListWidgetItem()
            item.setText(arg.name)
            self.args[id(item)] = arg
        current = self.ui.listArgs.item(data.get('current', 0))
        self._set_current_args(current)

    @Slot()
    def add_refer(self, data: ReferData):
        tb = self.ui.table
        row = tb.rowCount()
        tb.insertRow(row)
        for i, d in enumerate(data.tuple()):
            tb.setItem(row, i, QtWidgets.QTableWidgetItem(d))
        self.refers.append(data)

    @Slot()
    def start_target(self):
        if self.trace: self.chart.hide_markers(self.trace)
        self.trace = self.chart.make_new_trace()

    @Slot()
    def add_test_point(self, Vce: float, Ic: float):
        if not self.trace: 
            _log.error('no trace')
            return
        self.trace.add_test_point(Vce, Ic)

    @Slot()
    def export_refers(self):
        file, ext = QtWidgets.QFileDialog.getSaveFileName(
            self, '保存参考数据', filter='参考文件(*.ref)'
        )
        if not file: return

        try:
            _log.debug(f'导出参考数据到 {file}')
            refs = [r.dict() for r in self.refers]
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(refs, f, ensure_ascii=False, indent=4)
        except:
            _log.exception('导出参考数据失败')

    @Slot()
    def apply_refers(self):
        self.refersApplied.emit([r.dict() for r in self.refers])
