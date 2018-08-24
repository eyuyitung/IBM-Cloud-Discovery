@ECHO OFF

rem ***************** Edit these default parameters ********************

rem python directory:
set PYDIR="C:\Program Files\Python36\python.exe"

set MIDNIGHT="Y"

rem **************** edit nothing beyond this point *********************

echo Copyright (c) 2018 Cirba Inc. D/B/A Densify. All Rights Reserved.

set fpath=%~sdp0
set HOURS=0
set NAME=test


IF "%1"=="" (
	set /p HOURS=Please enter your desired sample size in hours: 
	set /p NAME=Please enter username specified in config.py: 
	set /p MIDNIGHT=Would you like metrics collected up to UTC midnight yesterday [Y/N]: 
)

if NOT %HOURS%=="0" (
	echo __________________  Collecting VSI's from provided credentials ...  __________________________
	
	call:discoveryFunc %HOURS%, %NAME% %MIDNIGHT%
	GOTO:EOF
)


:discoveryFunc

echo Clearing previous config ...
for /f %%i in ('dir /b %fpath%conf') do 2>NUL del /q %fpath%conf\%%i
2>NUL del /q %fpath%workload.csv
2>NUL del /q %fpath%attributes.csv
2>NUL del /q %fpath%config.csv


ECHO  - Step 1 - IBM Discovery
%PYDIR% %fpath%src\main.py -t %~1 -m %~2

IF errorlevel 1 GOTO:END

ECHO  - Step 2 - IBM Config
move %fpath%config.csv %fpath%conf\config.csv
move %fpath%attributes.csv %fpath%conf\attributes.csv
move %fpath%workload.csv %fpath%conf\workload.csv
IF errorlevel 1	GOTO:END 

ECHO  - Step 3 - Creating Manifest
call "%CIRBA_HOME%\bin\audit-converter.bat" -m %fpath%conf\ "IBM-%~2"
IF errorlevel 1 GOTO:END

ECHO  - Step 4 - Creating Repository
call "%CIRBA_HOME%\bin\audit-converter.bat" %fpath%conf\ %fpath%repo\
IF errorlevel 1 GOTO:END

ECHO  - Step 5 - Loading Repository
call "%CIRBA_HOME%\bin\load-repository.bat" %fpath%repo\ -o
IF errorlevel 1 GOTO:END

ECHO  - Step 6 - Move Repos to Hist directory
xcopy repo\* hist\* /s /i /q /Y
rmdir /s /q repo\
mkdir repo
IF errorlevel 1 GOTO:END

rem ECHO  - Step 7 - Import Attributes
rem call "%CIRBA_HOME%\bin\data-tools.bat" ImportAttributes -f %fpath%conf\
rem IF errorlevel 1 GOTO:END

:END

IF errorlevel 1 echo Exiting program ...
pause
