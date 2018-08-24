@ECHO OFF

rem ***************** Edit these default parameters ********************

rem python directory:
set PYDIR="C:\Program Files\Python36\python.exe"


rem **************** edit nothing beyond this point *********************

echo Copyright (c) 2018 Cirba Inc. D/B/A Densify. All Rights Reserved.


set ERROR="f"
set fpath=%~sdp0


IF "%1"=="" (
	echo one week is 168 hours, month is 720 hours, cannot sample beyond 6 weeks [168 hours]
	set /p HOURS=Please enter your desired sample size in hours: 
	set /p NAME=Please enter username specified in config.py: 
	echo __________________  Collecting VSI's from provided credentials ...  __________________________
	call:discoveryFunc %HOURS%
	GOTO:EOF
)

:discoveryFunc

echo Clearing previous config ...
for /f %%i in ('dir /b %fpath%conf') do 2>NUL del /q %fpath%conf\%%i
2>NUL del /q %fpath%workload.csv
2>NUL del /q %fpath%config.csv
2>NUL del /q %fpath%attributes.csv

set temp=%~1

ECHO  - Step 1 - IBM Discovery
%PYDIR% %fpath%src\main.py -t %~1 

IF errorlevel 1 GOTO:END

ECHO  - Step 2 - IBM Config
move %fpath%config.csv %fpath%conf\config.csv
move %fpath%attributes.csv %fpath%conf\attributes.csv
move %fpath%workload.csv %fpath%conf\workload.csv
IF errorlevel 1 (
	GOTO:END 
	set FILES="f"
)
ECHO  - Step 3 - Creating Manifest
call "%CIRBA_HOME%\bin\audit-converter.bat" -m %fpath%conf\ "IBM-%NAME%"
IF errorlevel 1 GOTO:END

ECHO  - Step 4 - Creating Repository
call "%CIRBA_HOME%\bin\audit-converter.bat" %fpath%conf\ %fpath%repo\
IF errorlevel 1 GOTO:END

ECHO  - Step 5 - Set systems to deleted
echo skipping step
rem call "%CIRBA_HOME%\bin\data-tools.bat" runscriptv1 -f %fpath%attr_update.txt -P PROJECT=%PROJECT%
IF errorlevel 1 GOTO:END

ECHO  - Step 6 - Loading Repository
call "%CIRBA_HOME%\bin\load-repository.bat" %fpath%repo\ -o
IF errorlevel 1 GOTO:END

ECHO  - Step 7 - Move Repos to Hist directory
xcopy repo\* hist\* /s /i /q /Y
rmdir /s /q repo\
mkdir repo

ECHO  - Step 8 - Import Attributes
call "%CIRBA_HOME%\bin\data-tools.bat" ImportAttributes -f %fpath%conf\
IF errorlevel 1 GOTO:END

:END

IF errorlevel 1 echo Exiting program ...
pause
