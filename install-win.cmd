@echo off
setlocal enabledelayedexpansion
pushd "%~dp0"

set _ID=OwonVdsTiny
set _NAME=OWON VDS1022 Oscilloscope
set _PUBLISHER=Fujian Lilliput Optoelectronics Technology Co.,Ltd
set _HOMEPAGE=https://github.com/florentbr/Owon-VDS1022
set _HELPLINK=https://owon.com.hk
set /p _VERSION=<version.txt
set _ARCH=%PROCESSOR_ARCHITECTURE%
set _PATH=%PATH%

set PATH=%SYSTEMROOT%\System32


echo ===========================================================
echo  Install %_NAME% (x%_ARCH:~-2%)
echo ===========================================================

echo Check environment ...

reg query "HKU\S-1-5-19\Environment" >nul 2>nul || goto :err_permissions
if not exist "lib\win\%_ARCH%" goto :err_architecture
if not exist "%APPDATA%" goto :err_appdata


echo Check driver ...

find /c /i "{eb781aaf-9c70-4523-a5df-642a87eca567}" "%SYSTEMROOT%\INF\oem*.inf" >nul 2>nul || (
	echo Install driver ...
	pnputil >nul || goto :err_driver
	pnputil /add-driver "lib\win\usb_device.inf" /install >nul
	echo Check driver ...
	pnputil /enum-drivers | find /i "{eb781aaf-9c70-4523-a5df-642a87eca567}" >nul || goto :err_driver
)


echo Locate Java from JAVA_HOME and PATH environment variables ...

call "%JAVA_BIN%\java.exe" -version 2>nul && goto :end_locate_java

set JAVA_BIN=%%JAVA_HOME%%\bin
call "%JAVA_BIN%\java.exe" -version 2>nul && goto :end_locate_java

for %%i in ("java.exe") do for %%j in ("%%~dp$_PATH:i.") do set JAVA_BIN=%%~fj
call "%JAVA_BIN%\java.exe" -version 2>nul || goto :err_java

:end_locate_java
call echo %JAVA_BIN%

if not exist "%JAVA_HOME%\bin" if /i "%JAVA_BIN:~-4%" == "\bin" (
	echo Add environment variable JAVA_HOME ...
	set "JAVA_HOME=%JAVA_BIN:~0,-4%"
	set "JAVA_BIN=%%JAVA_HOME%%\bin"
	reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v "JAVA_HOME" /t "REG_SZ" /d "!JAVA_HOME!" /f >nul
	setx /m "JAVA_HOME" "!JAVA_HOME!" >nul 2>nul
)

if /i "%_ARCH%" == "amd64" call "%JAVA_BIN%\java.exe" -XshowSettings -version 2>&1 | find "os.arch = x86" >nul && (
	echo Java is 32 bits, switching to x86 install ...
	"%SYSTEMROOT%\SysWOW64\cmd.exe" /c "%0"
	popd & exit /b %errorlevel%
)


echo Install Microsoft C Runtime 2010 Library dependency ...

xcopy "lib\win\%_ARCH%\msv*100.dll" "%SYSTEMROOT%\System32\" /d /y /c >nul 2>nul


echo Install files to %PROGRAMFILES%\%_ID% ...

rmdir /s /q "%PROGRAMFILES%\%_ID%" >nul 2>nul

xcopy "doc"                            "%PROGRAMFILES%\%_ID%\doc"      /y /i /e >nul || goto :err_file
xcopy "fwr"                            "%PROGRAMFILES%\%_ID%\fwr"      /y /i /e >nul || goto :err_file
xcopy "jar"                            "%PROGRAMFILES%\%_ID%\jar"      /y /i /e >nul || goto :err_file
xcopy "lib\win\%_ARCH%\LibusbJava.dll" "%PROGRAMFILES%\%_ID%\lib\"     /y       >nul || goto :err_file
xcopy "lib\win\%_ARCH%\rxtxSerial.dll" "%PROGRAMFILES%\%_ID%\lib\"     /y       >nul || goto :err_file
xcopy "version.txt"                    "%PROGRAMFILES%\%_ID%\"         /y       >nul || goto :err_file
copy  "ico\icon48.ico"                 "%PROGRAMFILES%\%_ID%\icon.ico" /y       >nul || goto :err_file

> "%PROGRAMFILES%\%_ID%\launch.cmd" (
	echo @pushd "%%~dp0"
	echo "%JAVA_BIN%\java.exe" -Djava.library.path="%%CD%%\lib" -Duser.dir="%%APPDATA%%\%_ID%" -Dsun.java2d.dpiaware=false -cp "%%CD%%\jar\*" com.owon.vds.tiny.Main
)


echo Create uninstall and menu shortcut %_NAME% ...

set /a _SIZE=0
for /r "%PROGRAMFILES%\%_ID%" %%i in (*) do set /a _SIZE+=%%~zi/1024

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
	echo CmdLine = -1, "%JAVA_BIN%", "javaw.exe -Djava.library.path=""%%01%%\lib"" -Duser.dir=""%%APPDATA%%\%_ID%"" -Dsun.java2d.dpiaware=false -cp ""%%01%%\jar\*"" com.owon.vds.tiny.Main"
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


echo Clear preferences in %APPDATA%\%_ID% ...

del /s /q "%APPDATA%\%_ID%\preferences*" >nul 2>nul


echo Done !
popd & pause & exit /b


:err_permissions
1>&2 echo Error: This script requires elevated privileges.
1>&2 echo   Right click on the file and select Run as administrator,
1>&2 echo   or run this script from an admin command prompt.
popd & pause & exit /b 1

:err_architecture
1>&2 echo Error: Architecture "%_ARCH%" not supported.
popd & pause & exit /b 1

:err_appdata
1>&2 echo Error: Environement variable "APPDATA" is not set or invalid.
popd & pause & exit /b 1

:err_java
1>&2 echo Error: java.exe not found or failed to run.
1>&2 echo   Environement variable "JAVA_HOME" or "PATH" is likely not set or invalid.
1>&2 echo   To install Java, visit adoptopenjdk.net or java.com
popd & pause & exit /b 1

:err_driver
1>&2 echo Error: Failed to install the driver.
1>&2 echo   Try to install the driver manually via device manager once the device is plugged.
1>&2 echo   Driver: %CD%\lib\win
popd & pause & exit /b 1

:err_file
1>&2 echo Error: Failed to copy to program files.
popd & pause & exit /b 1

:err_register
1>&2 echo Error: Failed to create uninstall and menu shortcut.
popd & pause & exit /b 1
