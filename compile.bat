@echo off
set NAME=TeardownVC
set SCRIPT=TeardownVC.py
set ICON=icon2.ico

echo Compiling program
python -m nuitka --onefile --standalone --deployment --windows-console-mode=disable --windows-icon-from-ico="%ICON%" --output-filename="%NAME%.exe" "%SCRIPT%"

echo Cleaning up build artifacts...
if exist "%NAME%.build" rmdir /s /q "%NAME%.build"
if exist "%NAME%.onefile-build" rmdir /s /q "%NAME%.onefile-build"
if exist "%NAME%.dist" rmdir /s /q "%NAME%.dist"

echo %NAME%.exe is ready
