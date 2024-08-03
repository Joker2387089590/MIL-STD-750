# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main.ui'
##
## Created by: Qt User Interface Compiler version 6.7.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QFormLayout,
    QGridLayout, QLabel, QLineEdit, QMainWindow,
    QMenuBar, QPushButton, QSizePolicy, QSpacerItem,
    QStatusBar, QVBoxLayout, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(993, 727)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.gridLayout_3 = QGridLayout()
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.gridLayout = QGridLayout()
        self.gridLayout.setObjectName(u"gridLayout")
        self.label_2 = QLabel(self.centralwidget)
        self.label_2.setObjectName(u"label_2")

        self.gridLayout.addWidget(self.label_2, 2, 0, 1, 1)

        self.label_3 = QLabel(self.centralwidget)
        self.label_3.setObjectName(u"label_3")

        self.gridLayout.addWidget(self.label_3, 3, 0, 1, 1)

        self.port = QComboBox(self.centralwidget)
        self.port.setObjectName(u"port")

        self.gridLayout.addWidget(self.port, 3, 1, 1, 1)

        self.label = QLabel(self.centralwidget)
        self.label.setObjectName(u"label")

        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)

        self.power = QLineEdit(self.centralwidget)
        self.power.setObjectName(u"power")

        self.gridLayout.addWidget(self.power, 2, 1, 1, 1)

        self.dmm = QLineEdit(self.centralwidget)
        self.dmm.setObjectName(u"dmm")

        self.gridLayout.addWidget(self.dmm, 1, 1, 1, 1)

        self.btnDmm = QPushButton(self.centralwidget)
        self.btnDmm.setObjectName(u"btnDmm")

        self.gridLayout.addWidget(self.btnDmm, 1, 2, 1, 1)

        self.btnPower = QPushButton(self.centralwidget)
        self.btnPower.setObjectName(u"btnPower")

        self.gridLayout.addWidget(self.btnPower, 2, 2, 1, 1)

        self.btnPort = QPushButton(self.centralwidget)
        self.btnPort.setObjectName(u"btnPort")

        self.gridLayout.addWidget(self.btnPort, 3, 2, 1, 1)

        self.btnAll = QPushButton(self.centralwidget)
        self.btnAll.setObjectName(u"btnAll")

        self.gridLayout.addWidget(self.btnAll, 0, 2, 1, 1)

        self.label_4 = QLabel(self.centralwidget)
        self.label_4.setObjectName(u"label_4")

        self.gridLayout.addWidget(self.label_4, 0, 0, 1, 2)


        self.gridLayout_3.addLayout(self.gridLayout, 0, 0, 1, 2)

        self.gridLayout_2 = QGridLayout()
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.btnVread = QPushButton(self.centralwidget)
        self.btnVread.setObjectName(u"btnVread")

        self.gridLayout_2.addWidget(self.btnVread, 2, 2, 1, 1)

        self.label_10 = QLabel(self.centralwidget)
        self.label_10.setObjectName(u"label_10")

        self.gridLayout_2.addWidget(self.label_10, 0, 0, 1, 3)

        self.Vread = QDoubleSpinBox(self.centralwidget)
        self.Vread.setObjectName(u"Vread")
        self.Vread.setReadOnly(True)

        self.gridLayout_2.addWidget(self.Vread, 2, 1, 1, 1)

        self.label_8 = QLabel(self.centralwidget)
        self.label_8.setObjectName(u"label_8")

        self.gridLayout_2.addWidget(self.label_8, 1, 0, 1, 1)

        self.label_9 = QLabel(self.centralwidget)
        self.label_9.setObjectName(u"label_9")

        self.gridLayout_2.addWidget(self.label_9, 2, 0, 1, 1)

        self.Vout = QDoubleSpinBox(self.centralwidget)
        self.Vout.setObjectName(u"Vout")

        self.gridLayout_2.addWidget(self.Vout, 1, 1, 1, 1)

        self.btnVout = QPushButton(self.centralwidget)
        self.btnVout.setObjectName(u"btnVout")

        self.gridLayout_2.addWidget(self.btnVout, 1, 2, 1, 1)

        self.label_11 = QLabel(self.centralwidget)
        self.label_11.setObjectName(u"label_11")

        self.gridLayout_2.addWidget(self.label_11, 3, 0, 1, 1)

        self.btnRset = QPushButton(self.centralwidget)
        self.btnRset.setObjectName(u"btnRset")

        self.gridLayout_2.addWidget(self.btnRset, 3, 2, 1, 1)

        self.Rset = QComboBox(self.centralwidget)
        self.Rset.setObjectName(u"Rset")

        self.gridLayout_2.addWidget(self.Rset, 3, 1, 1, 1)

        self.gridLayout_2.setColumnStretch(1, 1)

        self.gridLayout_3.addLayout(self.gridLayout_2, 1, 0, 1, 1)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.label_5 = QLabel(self.centralwidget)
        self.label_5.setObjectName(u"label_5")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.label_5)

        self.vcc = QDoubleSpinBox(self.centralwidget)
        self.vcc.setObjectName(u"vcc")

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.vcc)

        self.label_6 = QLabel(self.centralwidget)
        self.label_6.setObjectName(u"label_6")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label_6)

        self.ic = QDoubleSpinBox(self.centralwidget)
        self.ic.setObjectName(u"ic")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.ic)

        self.label_7 = QLabel(self.centralwidget)
        self.label_7.setObjectName(u"label_7")

        self.formLayout.setWidget(0, QFormLayout.SpanningRole, self.label_7)


        self.gridLayout_3.addLayout(self.formLayout, 1, 1, 1, 1)


        self.verticalLayout.addLayout(self.gridLayout_3)

        self.verticalSpacer = QSpacerItem(20, 426, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 993, 22))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.label_2.setText(QCoreApplication.translate("MainWindow", u"\u7535\u6e90Resource", None))
        self.label_3.setText(QCoreApplication.translate("MainWindow", u"\u7535\u963b\u7bb1COM\u53e3", None))
        self.label.setText(QCoreApplication.translate("MainWindow", u"\u4e07\u7528\u8868Resource", None))
        self.btnDmm.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5", None))
        self.btnPower.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5", None))
        self.btnPort.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5", None))
        self.btnAll.setText(QCoreApplication.translate("MainWindow", u"\u5168\u90e8\u8fde\u63a5", None))
        self.label_4.setText(QCoreApplication.translate("MainWindow", u"\u8bbe\u5907\u8fde\u63a5", None))
        self.btnVread.setText(QCoreApplication.translate("MainWindow", u"\u7acb\u5373\u91c7\u96c6", None))
        self.label_10.setText(QCoreApplication.translate("MainWindow", u"\u624b\u52a8\u63a7\u5236", None))
        self.Vread.setSuffix(QCoreApplication.translate("MainWindow", u"V", None))
        self.label_8.setText(QCoreApplication.translate("MainWindow", u"\u8f93\u51fa\u7535\u538b", None))
        self.label_9.setText(QCoreApplication.translate("MainWindow", u"\u91c7\u96c6\u7535\u538b", None))
        self.Vout.setSuffix(QCoreApplication.translate("MainWindow", u"V", None))
        self.btnVout.setText(QCoreApplication.translate("MainWindow", u"\u91cd\u65b0\u8bbe\u7f6e", None))
        self.label_11.setText(QCoreApplication.translate("MainWindow", u"\u7535\u963b\u963b\u503c", None))
        self.btnRset.setText(QCoreApplication.translate("MainWindow", u"\u91cd\u65b0\u8bbe\u7f6e", None))
        self.label_5.setText(QCoreApplication.translate("MainWindow", u"V<sub>ce</sub>", None))
        self.vcc.setSuffix(QCoreApplication.translate("MainWindow", u"V", None))
        self.label_6.setText(QCoreApplication.translate("MainWindow", u"I<sub>C</sub>", None))
        self.ic.setSuffix(QCoreApplication.translate("MainWindow", u"A", None))
        self.label_7.setText(QCoreApplication.translate("MainWindow", u"\u7528\u6237\u53c2\u6570", None))
    # retranslateUi

