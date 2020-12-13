@echo off
setlocal

pushd "%~dp0"

set _ID=OwonVdsTiny
set _NAME=OWON VDS1022 Oscilloscope
set _PUBLISHER=Fujian Lilliput Optoelectronics Technology Co.,Ltd
set _HOMEPAGE=https://github.com/florentbr/Owon-VDS1022
set _HELPLINK=https://owon.com.hk
set /p _VERSION=<".\version.txt"
set _ARCH=%PROCESSOR_ARCHITECTURE%
set _PATH=%PATH%

set PATH=%SYSTEMROOT%\System32


echo ===========================================================
echo  Install %_NAME%
echo ===========================================================

echo Check environment ...

reg query "HKU\S-1-5-19\Environment" >nul 2>nul || goto :err_permissions
if not exist ".\lib\win\%_ARCH%\" goto :err_architecture
if not exist "%APPDATA%" goto :err_env_appdata


echo Check driver ...

find /c /i "{eb781aaf-9c70-4523-a5df-642a87eca567}" "%SYSTEMROOT%\INF\oem*.inf" >nul 2>nul || (
	echo Install driver ...
	pnputil >nul || goto :err_driver
	pnputil /add-driver ".\lib\win\usb_device.inf" /install >nul
	echo Check driver ...
	pnputil /enum-drivers | find /i "{eb781aaf-9c70-4523-a5df-642a87eca567}" >nul || goto :err_driver
)


echo Get Java from JAVA_HOME ...

if exist "%JAVA_HOME%\bin\javaw.exe" goto :end_locate_java

echo Locate Java in PATH ...

for %%I in ("javaw.exe") do for %%J in ("%%~dp$_PATH:I..") do set "JAVA_HOME=%%~fJ"
if not exist "%JAVA_HOME%\bin\javaw.exe" goto :err_java_path

echo Add missing environment variable JAVA_HOME ...

reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v "JAVA_HOME" /t "REG_SZ" /d "%JAVA_HOME%" >nul
setx /m "JAVA_HOME" "%JAVA_HOME%" >nul 2>nul

:end_locate_java


echo Handle Java bitness ...

"%JAVA_HOME%\bin\java.exe" -version >nul 2>nul || goto :err_java_run

if /i [%_ARCH%] equ [AMD64] "%JAVA_HOME%\bin\java.exe" -version 2>&1 | find /i "64-Bit" >nul || (
	echo Switch to 32 bits install ...
	"%SYSTEMROOT%\SysWOW64\cmd.exe" /c "%0"
	exit /b %errorlevel%
)


echo Install Microsoft C Runtime 2010 Library dependency ...

xcopy ".\lib\win\%_ARCH%\msv*100.dll" "%SYSTEMROOT%\System32\" /d /y /c >nul 2>nul


echo Install program files ...

rmdir "%PROGRAMFILES%\%_ID%" /s /q >nul 2>nul

xcopy ".\doc\*"                          "%PROGRAMFILES%\%_ID%\doc\"     /y /e >nul || goto :err_file
xcopy ".\fwr\*.bin"                      "%PROGRAMFILES%\%_ID%\fwr\"     /y    >nul || goto :err_file
xcopy ".\jar\*.jar"                      "%PROGRAMFILES%\%_ID%\jar\"     /y    >nul || goto :err_file
xcopy ".\lib\win\%_ARCH%\LibusbJava.dll" "%PROGRAMFILES%\%_ID%\lib\"     /y    >nul || goto :err_file
xcopy ".\lib\win\%_ARCH%\rxtxSerial.dll" "%PROGRAMFILES%\%_ID%\lib\"     /y    >nul || goto :err_file
xcopy ".\version.txt"                    "%PROGRAMFILES%\%_ID%\"         /y    >nul || goto :err_file
copy  ".\ico\icon48.ico"                 "%PROGRAMFILES%\%_ID%\icon.ico" /y    >nul || goto :err_file


echo Create uninstall and menu shortcut ...

set /a _SIZE=0
for /r "%PROGRAMFILES%\%_ID%" %%I in (*) do set /a _SIZE+=%%~zI/1024

> "%PROGRAMFILES%\%_ID%\setup.inf" (
	echo [Version]
	echo Signature="$Windows NT$"
	echo AdvancedINF=2.5
	echo.
	echo [DefaultInstall]
	echo AddReg = AddReg
	echo ProfileItems = AddMenu
	echo.
	echo [AddReg]
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "ProductID"       , 0x00000000, "%_ID%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "DisplayName"     , 0x00000000, "%_NAME% (x%_ARCH:~-2%)"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "DisplayIcon"     , 0x00000000, "%%01%%\icon.ico"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "DisplayVersion"  , 0x00000000, "%_VERSION%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "InstallLocation" , 0x00000000, "%%01%%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "UninstallString" , 0x00000000, "%%11%%\rundll32.exe advpack.dll,LaunchINFSection ""%%01%%\setup.inf"",UnInstall,3"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "Publisher"       , 0x00000000, "%_PUBLISHER%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "HelpLink"        , 0x00000000, "%_HELPLINK%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "URLInfoAbout"    , 0x00000000, "%_HOMEPAGE%"
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "EstimatedSize"   , 0x00010001, %_SIZE%
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "NoModify"        , 0x00010001, 1
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%", "NoRepair"        , 0x00010001, 1
	echo.
	echo [AddMenu]
	echo Name = "%_NAME%"
	echo CmdLine = -1, "%%JAVA_HOME%%\bin", "javaw.exe -Djava.library.path=""%%01%%\lib"" -Duser.dir=""%%APPDATA%%\%_ID%"" -cp ""%%01%%\jar\*"" com.owon.vds.tiny.Main"
	echo IconPath = -1, "%%01%%", "icon.ico"
	echo WorkingDir = -1, "%%01%%"
	echo.
	echo [Uninstall]
	echo DelReg = DelReg
	echo ProfileItems = DelMenu
	echo RunPostSetupCommands = DelDirs
	echo.
	echo [DelReg]
	echo HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%_ID%"
	echo.
	echo [DelMenu]
	echo Name="%_NAME%", 2
	echo.
	echo [DelDirs]
	echo %%11%%\rundll32.exe advpack.dll,DelNodeRunDLL32 "%%01%%" ; deletes this folder
	echo %%11%%\rundll32.exe advpack.dll,DelNodeRunDLL32 "%%16410%%\%_ID%" ; deletes folder in APPDATA
	echo.
)

rundll32 advpack.dll,LaunchINFSection "%PROGRAMFILES%\%_ID%\setup.inf",DefaultInstall,3 || goto :err_register


echo Clear previous settings ...

del /s /q "%APPDATA%\%_ID%\preferences*" >nul 2>nul


echo Done !
pause & exit /b


:err_permissions
1>&2 echo Error: This script requires elevated privileges.
1>&2 echo   Right click on the file and select Run as administrator,
1>&2 echo   or run this script from an admin command prompt.
pause & exit /b 1

:err_architecture
1>&2 echo Error: Architecture "%_ARCH%" not supported.
pause & exit /b 1

:err_env_appdata
1>&2 echo Error: Environement variable "APPDATA" is not set or invalid.
pause & exit /b 1

:err_java_path
1>&2 echo Error: Java not found.
1>&2 echo   Environement variable "JAVA_HOME" is not set or invalid.
1>&2 echo   Visit adoptopenjdk.net to install Java
1>&2 echo   If Java is already installed, search for setting JAVA_HOME
pause & exit /b 1

:err_java_run
1>&2 echo Error: Failed to run Java. Try to reinstall Java.
pause & exit /b 1

:err_driver
1>&2 echo Error: Failed to install the driver.
1>&2 echo   Try to install the driver manually via device manager once the device is plugged.
1>&2 echo   Driver location: %CD%\lib\win
pause & exit /b 1

:err_file
1>&2 echo Error: Failed to copy to program files.
pause & exit /b 1

:err_register
1>&2 echo Error: Failed to create uninstall and menu shortcut.
pause & exit /b 1
