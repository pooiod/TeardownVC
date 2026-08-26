@echo off
set NAME=TeardownVC
set SCRIPT=TeardownVC.py
set ICON=icon2.ico

pyinstaller --noconfirm --name "%NAME%" --icon "%ICON%" --noconsole --onefile "%SCRIPT%"

echo Finished compiling
