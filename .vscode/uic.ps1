Get-ChildItem -Recurse *.ui | ForEach-Object { pyside6-uic.exe $_.FullName -o "$($_.DirectoryName)/$($_.BaseName)_ui.py" }
