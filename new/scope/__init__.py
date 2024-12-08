import pyvisa, logging
from pyvisa.resources.usb import USBInstrument
from PySide6.QtWidgets import *
from .scope_ui import Ui_Form

log = logging.getLogger(__name__)

class Scope(QWidget):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.ui.btnScreen.clicked.connect(self.screen)
        self.ui.btnWave.clicked.connect(self.waveform)
    
    def screen(self):
        try:
            file, ext = QFileDialog.getSaveFileName(
                self, '截图保存路径',
                filter='PNG(*.png)'
            )
            if len(file) == 0: return

            rm = pyvisa.ResourceManager()
            scope: USBInstrument = rm.open_resource(
                # 'USB0::0x0957::0x17A2::MY54490191::INSTR'
                self.ui.resource.text()
            )

            # 截屏
            png = scope.query_binary_values(
                ':DISPlay:DATA? PNG, COLor',
                delay=2.000,
                datatype='B',
                container=bytes)
            with open(file, 'wb') as f:
                f.write(png)
        except:
            log.exception('截图失败')

    def waveform(self):
        try:
            file, ext = QFileDialog.getSaveFileName(
                self, '波形数据保存路径',
                filter='CSV(*.csv)'
            )
            if not file: return

            rm = pyvisa.ResourceManager()
            scope: USBInstrument = rm.open_resource(
                # 'USB0::0x0957::0x17A2::MY54490191::INSTR'
                self.ui.resource.text()
            )

            input_channel = self.ui.channel.currentText()
            wfm_fmt = "WORD"

            def do_command(cmd: str):
                print(f'write: {cmd}')
                scope.write(cmd)
                scope.query('*OPC?')

            def do_query_string(cmd: str):
                return scope.query(cmd)

            def do_query_number(cmd: str):
                return float(scope.query(cmd))

            do_command(f":WAVeform:SOURce {input_channel}")
            qresult = do_query_string(":WAVeform:SOURce?")
            print(f"Waveform source: {qresult}")
            # Set the waveform points mode.
            do_command(":WAVeform:POINts:MODE RAW")
            qresult = do_query_string(":WAVeform:POINts:MODE?")
            print(f"Waveform points mode: {qresult}")
            # Get the number of waveform points available.
            do_command(":WAVeform:POINts 10240")
            qresult = do_query_string(":WAVeform:POINts?")
            print(f"Waveform points available: {qresult}")
            # Choose the format of the data returned (BYTE or WORD):
            do_command(f":WAVeform:FORMat {wfm_fmt}")
            qresult = do_query_string(":WAVeform:FORMat?")
            print(f"Waveform format: {qresult}")
            # Specify the byte order in WORD data.
            if wfm_fmt == "WORD":
                do_command(":WAVeform:BYTeorder LSBF")
                qresult = do_query_string(":WAVeform:BYTeorder?")
                print(f"Waveform byte order for WORD data: {qresult}")

            # Display the waveform settings from preamble:
            wav_form_dict = {
                0 : "BYTE",
                1 : "WORD",
                4 : "ASCii",
            }
            acq_type_dict = {
                0 : "NORMal",
                1 : "PEAK",
                2 : "AVERage",
                3 : "HRESolution",
            }
            preamble_string = do_query_string(":WAVeform:PREamble?")
            (
            wav_form, acq_type, wfmpts, avgcnt, x_increment, x_origin,
            x_reference, y_increment, y_origin, y_reference
            ) = preamble_string.split(",")
            print(f"Waveform format: {wav_form_dict[int(wav_form)]}")
            print(f"Acquire type: {acq_type_dict[int(acq_type)]}")
            print(f"Waveform points desired: {wfmpts}")
            print(f"Waveform average count: {avgcnt}")
            print(f"Waveform X increment: {x_increment}")
            print(f"Waveform X origin: {x_origin}")
            print(f"Waveform X reference: {x_reference}") # Always 0.
            print(f"Waveform Y increment: {y_increment}")
            print(f"Waveform Y origin: {y_origin}")
            print(f"Waveform Y reference: {y_reference}")
            
            # Get numeric values for later calculations.
            x_increment = float(x_increment)
            x_origin = float(x_origin)
            x_reference = float(x_reference)
            y_increment = float(y_increment)
            y_origin = float(y_origin)
            y_reference = float(y_reference)

            # Get the waveform data.
            datas = scope.query_binary_values(":WAVeform:DATA?", datatype='H')
            with open(file, 'w', encoding='utf-8') as f:
                f.write('time, value\n')
                for i, data in enumerate(datas):
                    time = (i - x_reference) * x_increment + x_origin
                    value = (data - y_reference) * y_increment
                    f.write(f'{time}, {value}\n')
        except:
            log.exception('保存波形数据失败')
