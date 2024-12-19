import logging
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
import numpy as np
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QTableWidgetItem
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
            self.ui.table.setRowCount(0)
            self.startRequested.emit()
        ui.btnStart.clicked.connect(try_start)
        ui.btnStop.clicked.connect(self.abortRequested.emit)

        self.chart = Chart()

        self.args: dict[int, ExecArgument] = {}
        self.items: dict[int, QListWidgetItem] = {}
        self.ui.listRefer.itemClicked.connect(self._set_current_item)
        self.ui.listRefer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listRefer.customContextMenuRequested.connect(self._show_context_menu)
        self.update_running_state(False)

    def _set_current_item(self, item: QListWidgetItem):
        self.ui.listRefer.setCurrentItem(item)
        arg = self.args[id(item)]

        # FIXME: change chart set_targets types
        targets = [
            ReferTarget(Vce=abs(i.Vce), Ic=i.Ic, Rc='', Re='') 
            for i in arg.items
        ]
        self.chart.set_targets(targets)

    def _show_context_menu(self, point: QtCore.QPoint):
        item = self.ui.listRefer.itemAt(point)
        if not item: return

        menu = QtWidgets.QMenu(self)
        # menu.addAction('编辑', lambda: self._try_edit(item))
        menu.addAction('删除', lambda: self._try_delete(item))
        menu.exec(self.ui.listRefer.mapToGlobal(point))

    def _try_edit(self, item: QListWidgetItem):
        ...

    def _try_delete(self, item: QListWidgetItem):
        ret = QMessageBox.warning(
            self, '删除参数', f'是否删除 {item.text()}?', 
            QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes: return

        xid = id(item)
        del self.args[xid]
        del self.items[xid]
        self.ui.listRefer.takeItem(self.ui.listRefer.row(item))

    def receive_refer_all_results(self, refer: ReferAllResult):
        arg = refer.argument
        earg = ExecArgument(
            name=arg.name, 
            type=arg.type,
            Vebo=refer.argument.Vebo,
            Vcbo=refer.argument.Vcbo,
            Vceo=refer.argument.Vceo,
            items=[],
        )
        for result in refer.results:
            earg.items.append(ExecItem(
                Vce=result.target_Vce,
                Ic=result.target_Ic,
                Vc=result.Vc,
                Ve=result.Ve,
                Rc=result.Rc,
                Re=result.Re,
                refer_Vce=result.Vce,
                refer_Ic=result.Ic,
                duration=arg.duration,
                Ve_delay=result.Ve_delay,
            ))

        item = QListWidgetItem(earg.name)
        self._add_exec_arg(earg, item)
        self.ui.listRefer.addItem(item)
        self._set_current_item(item)

    def _add_exec_arg(self, arg: ExecArgument, item: QListWidgetItem):
        xid = id(item)
        self.args[xid] = arg
        self.items[xid] = item
        self.ui.listRefer.setCurrentItem(item)

    @Slot()
    def update_running_state(self, running: bool):
        self.ui.btnStart.setDisabled(running)
        self.ui.btnStop.setEnabled(running)
        self.ui.listRefer.setDisabled(running)

    def get_arguments(self) -> ExecArgument:
        return self.args[id(self.ui.listRefer.currentItem())]

    def receive_exec_result(self, xresults: ExecResult):
        print(f'xresults.all_vce: {len(xresults.all_vce)}')
        print(f'xresults.all_dmm2: {len(xresults.all_dmm2)}')
        print(f'xresults.all_dmm3: {len(xresults.all_dmm3)}')
        print(f'xresults.all_ic: {len(xresults.all_ic)}')
        print(f'xresults.all_ie: {len(xresults.all_ie)}')
        vce = xresults.all_vce
        dmm2 = xresults.all_dmm2
        dmm3 = xresults.all_dmm3
        ic = xresults.all_ic
        ie = xresults.all_ie

        fig, (axv, axi) = plt.subplots(2, 1)
        axv: Axes
        axi: Axes
        
        def times(vs):
            d = len(vs) / xresults.rate
            return np.linspace(0, d, len(vs))
        axv.plot(times(vce), vce, label='Vce')
        axv.plot(times(dmm2), dmm2, label='Vbe(NPN)/Vcb(PNP)')
        axv.plot(times(dmm3), dmm3, label='Vcb(NPN)/Veb(PNP)')
        axi.plot(times(ic), ic, label='Ic')
        axi.plot(times(ie), ie, label='Ie')
        fig.show()

        b, e = xresults.output_range()
        print(f'{b = }, {e = }, ')
        errs = []
        if not xresults.pass_fail(vce[b:e]):
            errs.append('Vce')
        if not xresults.pass_fail(dmm2[b:e]):
            errs.append('Vbe' if xresults.type == 'NPN' else 'Vbc')
        if not xresults.pass_fail(dmm3[b:e]):
            errs.append('Vbe' if xresults.type != 'NPN' else 'Vbc')
        if not xresults.pass_fail(ic[b:e]):
            errs.append('Ic')
        if not xresults.pass_fail(ie[b:e]):
            errs.append('Ie')
        if errs:
            QMessageBox.warning(
                self,
                '持续测试失败',
                f'测量值 {",".join(errs)} 波动超过 10%')
        else:
            QMessageBox.information(
                self,
                '持续测试成功',
                '已完成测试，请查看数据表和图表'
            )

        base = self.ui.table.rowCount()
        for row, values in enumerate(zip(vce, dmm2, dmm3, ic, ie)):
            self.ui.table.insertRow(self.ui.table.rowCount())
            for col, value in enumerate(values):
                ii = QTableWidgetItem()
                ii.setText(str(value))
                self.ui.table.setItem(row + base, col, ii)    

    def save(self):
        current = self.ui.listRefer.row(self.ui.listRefer.currentItem())
        items = []
        for row in range(self.ui.listRefer.count()):
            item = self.ui.listRefer.item(row)
            arg = self.args[id(item)]
            items.append(asdict(arg))
        return dict(current=current, items=items)

    def load(self, data: dict):
        for d in data.get('items', []):
            d: dict
            arg = ExecArgument.fromdict(d)
            item = QListWidgetItem()
            xid = id(item)
            item.setText(arg.name)
            self.args[xid] = arg
            self.items[xid] = item
            self.ui.listRefer.addItem(item)

        current = self.ui.listRefer.item(data.get('current', 0))
        if current: self._set_current_item(current)

    def restart(self):
        self.chart.restart()

    def start_target(self):
        self.chart.make_trace()

    def add_test_point(self, Vce: float, Ic: float):
        self.chart.add_test_point(Vce, Ic)
