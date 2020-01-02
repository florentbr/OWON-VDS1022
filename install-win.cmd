@ECHO OFF
SETLOCAL

FOR %%I IN (%~dp0.) DO SET THIS_DIR=%%~fI
SET PATHS=%PATH%
SET PATH=%SYSTEMROOT%\System32

SET PK_ID=OwonVdsTiny
SET PK_ARCH=%PROCESSOR_ARCHITECTURE%
SET PK_NAME=OWON VDS1022 Oscilloscope
SET PK_PUBLISHER=Fujian Lilliput Optoelectronics Technology Co.,Ltd
SET PK_HOMEPAGE=https://github.com/florentbr/Owon-VDS1022
SET PK_HELPLINK=https://owon.com.hk
SET /P PK_VERSION=<"%THIS_DIR%\version.txt"

net session >NUL 2>NUL || GOTO:ERR_PERMISSIONS
IF NOT EXIST "%THIS_DIR%\lib\win\%PK_ARCH%\" GOTO:ERR_ARCHITECTURE


ECHO Check driver ...

FIND /C /I "{eb781aaf-9c70-4523-a5df-642a87eca567}" "%SYSTEMROOT%\INF\oem*.inf" >NUL || (
  ECHO Install driver ...
  pnputil /add-driver "%THIS_DIR%\lib\win\usb_device.inf" /install >NUL
  pnputil /enum-drivers | FIND /I "{eb781aaf-9c70-4523-a5df-642a87eca567}" >NUL || GOTO:ERR_DRIVER
)


ECHO Locate Java Runtime ...

SET JAVA_DIR=%%JAVA_HOME%%\bin
IF EXIST "%JAVA_HOME%\bin\javaw.exe" GOTO:END_LOCATE_JAVA

FOR /F %%I IN ("javaw.exe") DO SET "JAVA_DIR=%%~dp$PATHS:I"
IF EXIST "%JAVA_DIR%\javaw.exe" GOTO:END_LOCATE_JAVA

SET QUERY_JAVAHOME=REG QUERY "HKLM\SOFTWARE\JavaSoft\Java Runtime Environment" /v JavaHome /s
FOR /F "tokens=2*" %%a IN ('%QUERY_JAVAHOME% 2^>NUL ^| FIND "JavaHome"') DO SET "JAVA_DIR=%%~b\bin"
IF EXIST "%JAVA_DIR%\javaw.exe" GOTO:END_LOCATE_JAVA

SET QUERY_JAVAHOME=REG QUERY "HKLM\SOFTWARE\AdoptOpenJDK" /v Path /s
FOR /F "tokens=2*" %%a IN ('%QUERY_JAVAHOME% 2^>NUL ^| FIND "Path"') DO SET "JAVA_DIR=%%~b\bin"
IF EXIST "%JAVA_DIR%\javaw.exe" GOTO:END_LOCATE_JAVA

GOTO:ERR_JAVA
:END_LOCATE_JAVA


ECHO Install Microsoft C Runtime Library dependency ...

>NUL XCOPY /D /Y /C "%THIS_DIR%\lib\win\%PK_ARCH%\msv*100.dll" "%SYSTEMROOT%\System32\"


ECHO Install application files ...

>NUL 2>NUL RMDIR /S /Q "%PROGRAMFILES%\%PK_ID%"
>NUL XCOPY /Y /E "%THIS_DIR%\doc\*"                    "%PROGRAMFILES%\%PK_ID%\doc\"
>NUL XCOPY /Y /E "%THIS_DIR%\fwr\*"                    "%PROGRAMFILES%\%PK_ID%\fwr\"
>NUL XCOPY /Y /E "%THIS_DIR%\jar\*.jar"                "%PROGRAMFILES%\%PK_ID%\jar\"
>NUL XCOPY /Y /E "%THIS_DIR%\lib\win\%PK_ARCH%\*.dll"  "%PROGRAMFILES%\%PK_ID%\lib\"
>NUL COPY /Y     "%THIS_DIR%\version.txt"              "%PROGRAMFILES%\%PK_ID%\version.txt"
>NUL COPY /Y     "%THIS_DIR%\ico\icon48.ico"           "%PROGRAMFILES%\%PK_ID%\icon.ico"

>NUL 2>NUL DEL /S /Q "%LOCALAPPDATA%\%PK_ID%\preferences*"


ECHO Register application and create shortcut ...

FOR /R "%PROGRAMFILES%\%PK_ID%" %%I IN (*) DO SET /A PK_APP_SIZE+=%%~zI/1024

( ECHO [Version]
  ECHO Signature="$Windows NT$"
  ECHO AdvancedINF=2.5
  ECHO.
  ECHO [DefaultInstall]
  ECHO AddReg = AddReg
  ECHO ProfileItems = AddMenu
  ECHO.
  ECHO [AddReg]
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "ProductID", , "%PK_ID%"
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "DisplayName", , "%PK_NAME%"
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "DisplayIcon", , "%%16422%%\%PK_ID%\icon.ico"
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "DisplayVersion", , "%PK_VERSION%"
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "InstallLocation", , "%%16422%%\%PK_ID%"
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "UninstallString", , "rundll32.exe advpack.dll,LaunchINFSection ""%%16422%%\%PK_ID%\setup.inf"",UnInstall,3"
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "Publisher", , "%PK_PUBLISHER%"
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "HelpLink", , "%PK_HELPLINK%"
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "URLInfoAbout", , "%PK_HOMEPAGE%"
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "EstimatedSize", 0x00010001, %PK_APP_SIZE%
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "NoModify", 0x00010001, 1
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%", "NoRepair", 0x00010001, 1
  ECHO.
  ECHO [AddMenu]
  ECHO Name = "%PK_NAME%"
  ECHO CmdLine = -1, "%JAVA_DIR%", "javaw.exe -Djava.library.path=""%%PROGRAMFILES%%\%PK_ID%\lib"" -Duser.dir=""%%LOCALAPPDATA%%\%PK_ID%"" -cp ""%%PROGRAMFILES%%\%PK_ID%\jar\*"" com.owon.vds.tiny.Main"
  ECHO IconPath = 16422, "%PK_ID%", "icon.ico"
  ECHO WorkingDir = 16422, "%PK_ID%"
  ECHO.
  ECHO [Uninstall]
  ECHO DelReg = DelReg
  ECHO ProfileItems = DelMenu
  ECHO RunPostSetupCommands = DelDirs
  ECHO.
  ECHO [DelReg]
  ECHO HKLM, "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%"
  ECHO.
  ECHO [DelMenu]
  ECHO Name="%PK_NAME%", 2
  ECHO.
  ECHO [DelDirs]
  ECHO rundll32.exe advpack.dll,DelNodeRunDLL32 "%%16422%%\%PK_ID%"
  ECHO rundll32.exe advpack.dll,DelNodeRunDLL32 "%%53%%\AppData\Local\%PK_ID%"
  ECHO.
) > "%PROGRAMFILES%\%PK_ID%\setup.inf"

rundll32.exe advpack.dll,LaunchINFSection "%PROGRAMFILES%\%PK_ID%\setup.inf",DefaultInstall,3


ECHO Done !
PAUSE & GOTO:EOF



:ERR_PERMISSIONS
1>&2 ECHO Error: This script requires elevated privileges.
1>&2 ECHO   Right click on the file and select Run as administrator,
1>&2 ECHO   or run this script from an admin command prompt.
PAUSE & GOTO:EOF

:ERR_ARCHITECTURE
1>&2 ECHO Error: Architecture "%PK_ARCH%" not supported.
PAUSE & GOTO:EOF

:ERR_JAVA
1>&2 ECHO Error: Java Runtime not found.
1>&2 ECHO   Environement variable "JAVA_HOME" is either not set or invalid.
1>&2 ECHO   To install, visit  adoptopenjdk.net  or  java.com
PAUSE & GOTO:EOF

:ERR_DRIVER
1>&2 ECHO Error: failed to install the driver.
1>&2 ECHO   Try to install the driver manually via device manager
1>&2 ECHO   Driver location: %THIS_DIR%\lib\win
START "" /B devmgmt.msc
PAUSE & GOTO:EOF
