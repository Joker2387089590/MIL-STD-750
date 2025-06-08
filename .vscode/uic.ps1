Get-ChildItem -Recurse *_ui.py | Remove-item
Get-ChildItem -Recurse *.ui | ForEach-Object { pyside6-uic.exe $_.FullName -o "$($_.DirectoryName)/$($_.BaseName)_ui.py" }
