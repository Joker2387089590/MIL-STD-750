

    @functools.cache
    def test(self, Vb, Vc):
        self.power_vc.set_voltage(Vc)
        self.power_vb.set_voltage(Vb)

        self.power_vc.set_output_state(True)
        self.power_vb.set_output_state(True)
        try:
            Vce = self.读取Vce()
            Ic = self.读取Ic()
            self.csv.writerow(dict(Vb=Vb, Vc=Vc, Vce=Vce, Ic=Ic))
            return Vce, Ic
        except Exception:
            traceback.print_exc()
            return math.nan, math.nan
        finally:
            self.power_vb.set_output_state(False)
            self.power_vc.set_output_state(False)

    def 读取Vce(self):
        return self.dmm.read_dc_volt()

    def 读取Ic(self):
        return self.dmm.read_dc_current()
        # return float(self.power_vc.instr.query('MEAS:CURR?'))

    def 开始测试(self):
        self.maxVc = 10
        self.maxVb = 5.5
        self.target_Vce = self.ui.Vce.value()
        self.target_Ic = self.ui.ic.value()
        self.csv_file = open(f'{datetime.datetime.now():%H-%M-%S}.csv', 'w', newline='', encoding='utf-8')
        self.csv = csv.DictWriter(self.csv_file, ['Vb', 'Vc', 'Vce', 'Ic'])

        self.chart_vce_ic.removeAllSeries()
        self.chart_vce_ic.ax.setRange(0, self.target_Vce * 1.5)
        self.chart_vce_ic.ay.setRange(0, self.target_Ic * 1.5)

        self.Vb = 1

        try:
            safe_Vc = None
            safe_Vb = None
            counter = 0

            begin = time.time()
            while True:
                line_vce_ic = QtCharts.QLineSeries(self.chart_vce_ic)
                self.chart_vce_ic.addSeries(line_vce_ic)
                line_vce_ic.attachAxis(self.chart_vce_ic.ax)
                line_vce_ic.attachAxis(self.chart_vce_ic.ay)

                self.Vc = self.target_Vce
                while True:
                    Vce, Ic = self.test(self.Vb, self.Vc)
                    counter += 1
                    print(f'[{counter}] Vb, Vc, Vce, Ic = {self.Vb}, {self.Vc}, {Vce}, {Ic}')

                    p2 = QtCore.QPointF(Vce, Ic)
                    # points_vce_ic.append(p2)
                    line_vce_ic.append(p2)
                    QtWidgets.QApplication.processEvents()

                    if Ic > self.target_Ic:
                        print(f'--- MAX Ic, Vc = {self.Vc}, Vb = {self.Vb}')
                        break
                    safe_Vc = self.Vc

                    self.Vc += 0.5
                    if self.Vc > self.maxVc:
                        raise Exception('FAIL Vc')
                if Vce > self.target_Vce:
                    print(f'--- MAX Vce, Vc = {self.Vc}, Vb = {self.Vb}')
                    break
                safe_Vb = self.Vb

                self.Vb += 0.2
                if self.Vb > self.maxVb:
                    raise Exception('FAIL Vb')
            end_Vb = self.Vb
            end_Vc = self.Vc

            counter = 0
            self.Vb = safe_Vb
            self.Vc = safe_Vc
            target = self.target_Vce * self.target_Ic
            total_distance = 0.0
            distances: list[tuple[float, float, float]] = []
            while self.Vb <= end_Vb:
                self.Vc = safe_Vc
                while self.Vc <= end_Vc:
                    Vce, Ic = self.test(self.Vb, self.Vc)
                    distance = abs(Vce * Ic - target)
                    total_distance += distance
                    print(f'[{counter}] Vb, Vc, Vce, Ic, distance = {self.Vb}, {self.Vc}, {Vce}, {Ic}, {distance}')
                    distances.append((self.Vb, self.Vc, distance))
                    self.Vc += 0.1
                self.Vb += 0.05
            
            result_Vb = 0.0
            result_Vc = 0.0
            for vb, vc, dis in distances:
                rate = dis / total_distance
                result_Vb += vb * rate
                result_Vc += vc * rate
            result_Vb = (result_Vb // 0.01) * 0.01
            result_Vc = (result_Vc // 0.01) * 0.01

            end = time.time()
            print(f'result: Vb = {result_Vb}, Vc = {result_Vc}; use time: {end - begin:.3f}s')
        except KeyboardInterrupt:
            pass
        except Exception as e:
            traceback.print_exc()
        finally:
            self.csv = None
            self.csv_file.close()