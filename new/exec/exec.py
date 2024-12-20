import logging
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
import numpy as np
from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QTableWidgetItem
from ..types import *
from ..chart import Chart
from ..table_csv import export_csv
from .exec_ui import Ui_ExecPanel

_log = logging.getLogger(__name__)

_npn_headers = ['目标Vce/V', '目标Ic/A', "Vce/V", "Vbe/V", "Vcb/V", "Ic", "Ie", 'Vc/V', 'Ve/V', 'Rc', 'Re']
_pnp_headers = ['目标Vce/V', '目标Ic/A', "Vce/V", "Vbc/V", "Veb/V", "Ic", "Ie", 'Vc/V', 'Ve/V', 'Rc', 'Re']

class _Var: 
    def __init__(self):
        self.column = 0

class ExecPanel(QtWidgets.QWidget):
    startRequested = Signal()
    abortRequested = Signal()

    def __init__(self, parent = None):
        super().__init__(parent)
        self.ui = ui = Ui_ExecPanel()
        ui.setupUi(self)

        self.chart = Chart()
        self.pass_fail: bool = True

        def try_start():
            self.ui.btnStart.setDisabled(True)
            self.ui.table.setRowCount(0)
            self.ui.tableResult.setRowCount(0)
            self.pass_fail = True
            self.startRequested.emit()
        ui.btnStart.clicked.connect(try_start)
        ui.btnStop.clicked.connect(self.abortRequested.emit)

        self.args: dict[int, ExecArgument] = {}
        self.items: dict[int, QListWidgetItem] = {}
        self.ui.listRefer.itemClicked.connect(self._set_current_item)
        self.ui.listRefer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listRefer.customContextMenuRequested.connect(self._show_context_menu)

        self.ui.btnExportData.clicked.connect(self.export_datas)
        self.ui.btnExportResult.clicked.connect(self.export_results)

        self.update_running_state(False)

    def _set_current_item(self, item: QListWidgetItem):
        self.ui.listRefer.setCurrentItem(item)
        arg = self.args[id(item)]
        self.chart.set_targets([(abs(i.Vce), i.Ic) for i in arg.items])
        
        headers = _npn_headers if arg.type == 'NPN' else _pnp_headers

        data_headers = ['编号']
        data_headers.extend(headers)
        self.ui.table.setColumnCount(len(data_headers))
        self.ui.table.setHorizontalHeaderLabels(data_headers)

        result_headers = ['编号', '判定']
        result_headers.extend(headers)
        self.ui.tableResult.setColumnCount(len(result_headers))
        self.ui.tableResult.setHorizontalHeaderLabels(result_headers)

    def current_number(self):
        return self.ui.editNo.text()

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
        self.ui.wNo.setDisabled(running)

    def get_arguments(self) -> ExecArgument:
        return self.args[id(self.ui.listRefer.currentItem())]

    def receive_exec_result(self, xresults: ExecResult):
        _log.debug(f'xresults.all_vce: {len(xresults.all_vce)}')
        _log.debug(f'xresults.all_dmm2: {len(xresults.all_dmm2)}')
        _log.debug(f'xresults.all_dmm3: {len(xresults.all_dmm3)}')
        _log.debug(f'xresults.all_ic: {len(xresults.all_ic)}')
        _log.debug(f'xresults.all_ie: {len(xresults.all_ie)}')

        vce = xresults.all_vce
        dmm2 = xresults.all_dmm2
        dmm3 = xresults.all_dmm3
        ic = xresults.all_ic
        ie = xresults.all_ie

        label_dmm2 = 'Vbe' if xresults.type == 'NPN' else 'Vbc'
        label_dmm3 = 'Vcb' if xresults.type == 'NPN' else 'Veb'

        # plot
        if self.ui.checkPlot.isChecked():
            fig, (axv, axi) = plt.subplots(2, 1)
            axv: Axes
            axi: Axes
            def times(vs):
                d = len(vs) / xresults.rate
                return np.linspace(0, d, len(vs))
            axv.plot(times(vce), vce, label='Vce')
            axv.plot(times(dmm2), dmm2, label=label_dmm2)
            axv.plot(times(dmm3), dmm3, label=label_dmm3)
            axi.plot(times(ic), ic, label='Ic')
            axi.plot(times(ie), ie, label='Ie')
            fig.show()

        b, e = xresults.output_range()
        _log.debug(f'[exec] result output range: {b = }, {e = }')

        avgs: list[float] = []
        errs = []
        def pass_fail(name: str, values: list[float]):
            if not values: values = [0]

            avg = sum(values) / len(values)
            avgs.append(avg)

            lower, upper = avg * 0.9, avg * 1.1
            if min(values) < lower or max(values) > upper:
                errs.append(name)

        pass_fail('Vce', vce[b:e])
        pass_fail(label_dmm2, dmm2[b:e])
        pass_fail(label_dmm3, dmm3[b:e])
        pass_fail('Ic', ic[b:e])
        pass_fail('Ie', ie[b:e])

        if not errs:
            is_pass = 'PASS'
        else:
            self.pass_fail = False
            QMessageBox.warning(self, '持续测试失败', f'测量值 {",".join(errs)} 波动超过 10%')
            is_pass = 'FAIL'

        # 添加数据表
        for values in zip(vce, dmm2, dmm3, ic, ie):
            var = _Var()
            row = self.ui.table.rowCount()
            self.ui.table.insertRow(row)
            def add_data(value):
                ii = QTableWidgetItem()
                ii.setText(str(value))
                self.ui.table.setItem(row, var.column, ii)
                var.column += 1

            add_data(self.current_number())
            add_data(xresults.item.Vce)
            add_data(xresults.item.Ic)
            for value in values: add_data(value)
            add_data(xresults.item.Vc)
            add_data(xresults.item.Ve)
            add_data(xresults.item.Rc)
            add_data(xresults.item.Re)

        # 添加判定表
        var = _Var()
        row = self.ui.tableResult.rowCount()
        self.ui.tableResult.insertRow(row)
        def add_result(value):
            ii = QTableWidgetItem()
            ii.setText(str(value))
            self.ui.tableResult.setItem(row, var.column, ii)
            var.column += 1

        for avg in avgs:
            add_result(self.current_number())
            add_result(is_pass)
            add_result(xresults.item.Vce)
            add_result(xresults.item.Ic)
            add_result(avg)
            add_result(xresults.item.Vc)
            add_result(xresults.item.Ve)
            add_result(xresults.item.Rc)
            add_result(xresults.item.Re)

    def receive_exec_all_results(self, results: ExecAllResult):
        if self.pass_fail:
            QMessageBox.information(
                self, '持续测试成功', '已完成测试，请查看数据表和图表'
            )

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

    def export_datas(self):
        if self.ui.table.rowCount() == 0:
            QMessageBox.information(self, '导出数据失败', '没有测试数据!')
            return
        path, ok = QtWidgets.QFileDialog.getSaveFileName(
            self, caption='导出数据', filter='CSV(*.csv)')
        if not ok: return
        export_csv(self.ui.table, path)

    def export_results(self):
        path, ok = QtWidgets.QFileDialog.getSaveFileName(
            self, caption='导出判定结果', filter='CSV(*.csv)')
        if not ok: return
        export_csv(self.ui.tableResult, path)
