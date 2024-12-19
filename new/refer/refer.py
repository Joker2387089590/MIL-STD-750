import logging, csv
from PySide6 import QtCore, QtGui, QtWidgets
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

class ReferPanel(QtWidgets.QWidget):
    startRequested = Signal()
    abortRequested = Signal()
    closed = Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = ui = Ui_ReferPanel()

        ui.setupUi(self)
        self._setup_charts()
        self._setup_args()

        def try_start():
            self.ui.btnStart.setDisabled(True)
            self.startRequested.emit()
        ui.btnStart.clicked.connect(try_start)
        ui.btnStop.clicked.connect(self.abortRequested.emit)

        ui.btnExport.clicked.connect(self.export_table)
        ui.btnClear.clicked.connect(self.clear_table)

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

    def _setup_args(self):
        self.args: dict[int, ReferArgument] = {}
        self.items: dict[int, QListWidgetItem] = {}

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
            arg = ReferArgument.fromdict(d)
            item = QListWidgetItem()
            xid = id(item)
            item.setText(arg.name)
            self.args[xid] = arg
            self.items[xid] = item
            self.ui.listArgs.addItem(item)

        current = self.ui.listArgs.item(data.get('current', 0))
        if current: self._set_current_args(current)
    
    @property
    def current_item(self):
        return self.ui.listArgs.currentItem()

    def _show_context_menu(self, point: QtCore.QPoint):
        item = self.ui.listArgs.itemAt(point)
        if not item: return
        menu = QtWidgets.QMenu(self)
        menu.addAction('编辑', lambda: self._try_edit(item))
        menu.addAction('删除', lambda: self._try_delete(item))
        menu.exec(self.ui.listArgs.mapToGlobal(point))

    def _set_current_args(self, item: QListWidgetItem):
        self.ui.listArgs.setCurrentItem(item)
        arg = self.args[id(item)]
        self.chart.set_targets(arg.targets)

    def _add_args(self, arg: ReferArgument, item: QListWidgetItem):
        xid = id(item)
        self.args[xid] = arg
        self.items[xid] = item
        self.ui.listArgs.setCurrentItem(item)

    def _try_add_args(self):
        names = {item.text() for id, item in self.items.items()}
        panel = ArgumentPanel(names, self)
        def accept():
            arg = panel.save()
            item = QListWidgetItem(arg.name)
            self._add_args(arg, item)
            self.ui.listArgs.addItem(item)
            self._set_current_args(item)
            self.closed.emit()
            
        panel.accepted.connect(accept)
        panel.open()

    def _try_edit(self, item: QListWidgetItem):
        xid = id(item)
        old_arg = self.args.pop(xid, None)
        if old_arg is None: return

        xitem = self.items.pop(xid, None)
        assert xitem is item

        names = {item.text() for id, item in self.items.items()}
        panel = ArgumentPanel(names, self)

        def accept():
            arg = panel.save()
            item.setText(arg.name)
            self._add_args(arg, item)
            self.closed.emit()
            self._set_current_args(item)

        def reject():
            self._add_args(old_arg, item)
            self._set_current_args(item)

        panel.accepted.connect(accept)
        panel.rejected.connect(reject)
        panel.load(old_arg)
        panel.open()

    def _try_delete(self, item: QListWidgetItem):
        ret = QMessageBox.warning(
            self, '删除参数', f'是否删除 {item.text()}?', 
            QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes: return

        xid = id(item)
        del self.args[xid]
        del self.items[xid]
        self.ui.listArgs.takeItem(self.ui.listArgs.row(item))
    
    @Slot()
    def update_running_state(self, running: bool):
        self.ui.btnStart.setDisabled(running)
        self.ui.btnStop.setEnabled(running)
        self.ui.listArgs.setDisabled(running)

    def get_arguments(self):
        return self.args[id(self.current_item)]

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
    
    def export_table(self):
        path, ok = QtWidgets.QFileDialog.getSaveFileName(
            self, caption='导出参考数据', filter='CSV(*.csv)')
        if not ok: return

        columns = range(self.ui.table.columnCount())
        header = [
            self.ui.table.horizontalHeaderItem(column).text()
            for column in columns
        ]
        with open(path, 'w') as csvfile:
            writer = csv.writer(csvfile, dialect='excel', lineterminator='\n')
            writer.writerow(header)
            for row in range(self.ui.table.rowCount()):
                writer.writerow(
                    self.ui.table.item(row, column).text()
                    for column in columns
                )
        
    def clear_table(self):
        ret = QtWidgets.QMessageBox.warning(
            self, 
            '清除参考数据表', 
            '是否清空数据（无法撤销！）',
            QtWidgets.QMessageBox.StandardButton.Yes,
            QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if ret == QtWidgets.QMessageBox.StandardButton.Yes:
            self.ui.table.setRowCount(0)
