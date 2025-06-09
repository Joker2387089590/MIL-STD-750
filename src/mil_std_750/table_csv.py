import csv
from PySide6.QtWidgets import QTableWidget

def export_csv(table: QTableWidget, path: str):
    columns = range(table.columnCount())
    header = [table.horizontalHeaderItem(column).text() for column in columns]
    with open(path, 'w') as file:
        writer = csv.writer(file, dialect='excel', lineterminator='\n')
        writer.writerow(header)
        for row in range(table.rowCount()):
            writer.writerow(table.item(row, column).text() for column in columns)
