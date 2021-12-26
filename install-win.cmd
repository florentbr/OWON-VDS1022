@echo off
pushd %~dp0
if [%1] == [goto] goto %2

set _ID=owon-vds-tiny
set _NAME=OWON VDS1022
set _FULLNAME=OWON VDS1022 Oscilloscope
set _DEVICE={eb781aaf-9c70-4523-a5df-642a87eca567}
set _PUBLISHER=Fujian Lilliput Optoelectronics Technology Co.,Ltd
set _HOMEPAGE=https://github.com/florentbr/Owon-VDS1022
set _PATH=%PATH%

set /p _VERSION=<version.txt || goto :err_archive

set PATH=%SYSTEMROOT%\System32;
if not defined LOCALAPPDATA set LOCALAPPDATA=%APPDATA%


echo ===========================================================
echo  Install %_NAME% %_VERSION%
echo  %_HOMEPAGE%
echo ===========================================================

net session >nul 2>nul || goto :err_permissions
if not exist "lib\win\%PROCESSOR_ARCHITECTURE%" goto :err_architecture
if not exist "%LOCALAPPDATA%" goto :err_appdata


echo Check driver ...

find /c /i "%_DEVICE%" "%SYSTEMROOT%\INF\oem*.inf" >nul || (
	echo Install driver ...
	pnputil >nul || goto :err_driver
	pnputil /add-driver "lib\win\usb_device.inf" /install >nul
	pnputil /enum-drivers | find /i "%_DEVICE%" >nul || goto :err_driver
	pnputil /scan-devices >nul
)


echo Try locate Java from JAVA_HOME environment variables ...

set "_JREDIR=%%JAVA_HOME%%\bin"
call "%_JREDIR%\java.exe" -version 2>nul && goto :end_locate_java

echo Try locate Java from PATH environment variables ...

for %%i in (java.exe) do for %%j in ("%%~dp$_PATH:i.") do set "_JREDIR=%%~fj"
call "%_JREDIR%\java.exe" -version 2>nul || goto :err_java
if /i "%_JREDIR:~-4%" neq "\bin" goto :end_locate_java

echo Add missing environment variable JAVA_HOME ...

set "JAVA_HOME=%_JREDIR:~0,-4%"
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v "JAVA_HOME" /t "REG_SZ" /d "%JAVA_HOME%" /f >nul
setx /m "JAVA_HOME" "%JAVA_HOME%" >nul 2>nul
set "_JREDIR=%%JAVA_HOME%%\bin"

:end_locate_java
call echo %_JREDIR%\java.exe

echo Check Java bitness ...

if /i "%PROCESSOR_ARCHITECTURE%" == "amd64" call "%_JREDIR%\java.exe" -XshowSettings -version 2>&1 | find "os.arch = x86" >nul && (
	echo Java is 32 bits, switching to x86 install ...
	%SYSTEMROOT%\SysWOW64\cmd.exe /d /c %0 goto :end_bitness_java
	popd & goto :eof
)

:end_bitness_java
set _ARCH=%PROCESSOR_ARCHITECTURE%


echo Clean previous install ...

xcopy "%APPDATA%\OwonVdsTiny\*" "%LOCALAPPDATA%\%_NAME%\" /y /i /e 2>nul >nul
rundll32 advpack.dll,LaunchINFSection "%PROGRAMFILES%\OwonVdsTiny\setup.inf",UnInstall,3 2>nul >nul
rmdir /s /q "%PROGRAMFILES%\OwonVdsTiny" "%APPDATA%\OwonVdsTiny" 2>nul >nul
rundll32 advpack.dll,LaunchINFSection "%PROGRAMFILES%\%_NAME%\setup.inf",UnInstall,3 2>nul >nul
rmdir /s /q "%PROGRAMFILES%\%_NAME%" 2>nul >nul
del /q "%LOCALAPPDATA%\%_NAME%\preferences*" 2>nul >nul


echo Install Microsoft C Runtime 2010 Library dependency ...

xcopy "lib\win\%_ARCH%\msvcp100.dll" "%SYSTEMROOT%\System32\" /y /d >nul || goto :err_file
xcopy "lib\win\%_ARCH%\msvcr100.dll" "%SYSTEMROOT%\System32\" /y /d >nul || goto :err_file


echo Install in %PROGRAMFILES%\%_NAME% ...

xcopy "doc\*"                          "%PROGRAMFILES%\%_NAME%\doc\" /y /i /e >nul || goto :err_file
xcopy "fwr\*.bin"                      "%PROGRAMFILES%\%_NAME%\fwr\" /y /i    >nul || goto :err_file
xcopy "lib\*.jar"                      "%PROGRAMFILES%\%_NAME%\lib\" /y /i    >nul || goto :err_file
xcopy "lib\win\%_ARCH%\LibusbJava.dll" "%PROGRAMFILES%\%_NAME%\lib\" /y /i    >nul || goto :err_file
xcopy "version.txt"                    "%PROGRAMFILES%\%_NAME%\"     /y       >nul || goto :err_file
xcopy "ico\icon.ico"                   "%PROGRAMFILES%\%_NAME%\"     /y       >nul || goto :err_file

> "%PROGRAMFILES%\%_NAME%\launch.cmd" (
	echo @pushd %%~dp0
	echo "%_JREDIR%\java.exe" -Dsun.java2d.dpiaware=false -cp lib\* com.owon.vds.tiny.Main
)

> "%PROGRAMFILES%\%_NAME%\uninstall.cmd" (
	echo if /i "%%PROCESSOR_ARCHITECTURE%%" neq "%_ARCH%" %SYSTEMROOT%\SysWOW64\cmd.exe /d /c %%0 ^& goto :eof
	echo @set PATH=%SYSTEMROOT%\System32;%SYSTEMROOT%\Sysnative;
	echo @if not defined LOCALAPPDATA set LOCALAPPDATA=%%APPDATA%%
	echo @for %%%%f in ^(%SYSTEMROOT%\INF\oem*.inf^) do @find /c /i "%_DEVICE%" %%%%f ^>nul ^&^& set OEM=%%%%~nxf
	echo pnputil /remove-device "USB\VID_5345&PID_1234\0" 2^>nul
	echo pnputil /delete-driver "%%OEM%%" /force 2^>nul
	echo rundll32 advpack.dll,LaunchINFSection "%%~dp0setup.inf",UnInstall,3
	echo start "" /b cmd /d /c rmdir /s /q "%%~dp0" "%%LOCALAPPDATA%%\%_NAME%"
)


echo Create menu shortcut and register for uninstall ...

set /a _SIZE=0
for /r "%PROGRAMFILES%\%_NAME%" %%i in (*) do set /a _SIZE+=%%~zi/1024

> "%PROGRAMFILES%\%_NAME%\setup.inf" (
	:: https://docs.microsoft.com/en-us/windows-hardware/drivers/install
	echo [Version]
	echo Signature = "$CHICAGO$"
	echo AdvancedINF = 2.5
	echo.
	echo [DefaultInstall]
	echo AddReg = AddReg
	echo ProfileItems = AddMenu
	echo.
	echo [AddReg]
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", ProductID      , , "%_ID%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", DisplayName    , , "%_NAME% (x%_ARCH:~-2%)"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", DisplayIcon    , , "%%01%%\icon.ico"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", DisplayVersion , , "%_VERSION%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", InstallLocation, , "%%01%%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", UninstallString, , """%%01%%\uninstall.cmd"""
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", Publisher      , , "%_PUBLISHER%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", URLInfoAbout   , , "%_HOMEPAGE%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", EstimatedSize  , 0x00010001, %_SIZE%
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", NoModify       , 0x00010001, 1
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%", NoRepair       , 0x00010001, 1
	echo.
	echo [AddMenu]
	echo Name = "%_FULLNAME%", 0
	echo CmdLine = -1, "%_JREDIR%", "javaw.exe -Dsun.java2d.dpiaware=false -cp lib\* com.owon.vds.tiny.Main"
	echo IconPath = -1, "%%01%%", "icon.ico"
	echo WorkingDir = -1, "%%01%%"
	echo.
	echo [Uninstall]
	echo DelReg = DelReg
	echo ProfileItems = DelMenu
	echo.
	echo [DelReg]
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_NAME%"
	echo.
	echo [DelMenu]
	echo Name = "%_FULLNAME%", 2
	echo.
)

rundll32 advpack.dll,LaunchINFSection "%PROGRAMFILES%\%_NAME%\setup.inf",DefaultInstall,2 || goto :err_register
dir /b "%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs\%_FULLNAME%.lnk" 2>nul >nul || goto :err_register


echo.
echo SUCCESS !
popd & pause >nul & exit \b 0


:err_permissions
>&2 echo Error: This script requires elevated privileges.
>&2 echo   Right click on the file and select Run as administrator,
>&2 echo   or run this script from an admin command prompt.
goto :failed

:err_architecture
>&2 echo Error: Architecture "%PROCESSOR_ARCHITECTURE%" not supported.
goto :failed

:err_appdata
>&2 echo Error: Environement variable "APPDATA" or "LOCALAPPDATA" is not set or invalid.
goto :failed

:err_java
>&2 echo Error: java.exe not found or failed to run.
>&2 echo   Environement variable "JAVA_HOME" or "PATH" is likely not set or invalid.
>&2 echo   Visit adoptium.net/releases.html and download/install OpenJDK 11 JRE .msi (~40Mb)
goto :failed

:err_driver
>&2 echo Error: Failed to install the driver.
>&2 echo   Try to install the driver manually via device manager once the device is plugged.
>&2 echo   Driver: %CD%\lib\win
goto :failed

:err_file
>&2 echo Error: Failed to copy.
goto :failed

:err_register
>&2 echo Error: Failed to create uninstall and menu shortcut.
goto :failed

:err_archive
>&2 echo Error: Failed to read version. Extract the files first.
goto :failed

:failed
color 4F
>&2 echo.
>&2 echo FAILED !
popd & pause >nul & exit \b 1
