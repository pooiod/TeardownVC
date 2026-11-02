@echo off
set NAME=TeardownVC
set SCRIPT=TeardownVC.py
set ICON=icon2.ico

echo Starting Nuitka compilation...
python -m nuitka --standalone --onefile --windows-console-mode=disable --windows-icon-from-ico="%ICON%" --output-filename="%NAME%.exe" "%SCRIPT%"

echo Cleaning up build cache folders...
if exist "%NAME%.build" rmdir /s /q "%NAME%.build"
if exist "%NAME%.dist" rmdir /s /q "%NAME%.dist"

echo Finished compiling
