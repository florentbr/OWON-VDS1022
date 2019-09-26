@ECHO OFF

SET THIS_DIR=%~dp0
SET THIS_DIR=%THIS_DIR:~0,-1%
SET ARCH=%PROCESSOR_ARCHITECTURE%
SET PATH=%SYSTEMROOT%;%SYSTEMROOT%\System32;%SYSTEMROOT%\System32\WindowsPowerShell\v1.0

where powershell 1>NUL 2>NUL || GOTO:ERR_POWERSHELL

SET    PK_ID=OwonVdsTiny
SET    PK_NAME=Owon VDS1022 Oscilloscope
SET /p PK_VERSION=<%THIS_DIR%\version.txt
SET    PK_MENU_LINK=%USERPROFILE%\Start Menu\Programs\%PK_NAME%.lnk
SET    PK_USRDIR=%USERPROFILE%\AppData\Local\%PK_ID%
SET    PK_PUBLISHER=Fujian Lilliput Optoelectronics Technology Co.,Ltd
SET    PK_HOMEPAGE=https://github.com/florentbr/Owon-VDS1022
SET    PK_INSTALLEDSIZE=0

IF /I "%ARCH%" == "amd64" (
	SET JRE_URL="https://javadl.oracle.com/webapps/download/AutoDL?BundleId=239858_230deb18db3e4014bb8e3e8324f81b43"
	GOTO:HANDLE_DRIVER
)
IF /I "%ARCH%" == "x86" (
	SET JRE_URL="https://javadl.oracle.com/webapps/download/AutoDL?BundleId=239856_230deb18db3e4014bb8e3e8324f81b43"
	GOTO:HANDLE_DRIVER
)
GOTO:ERR_ARCHITECTURE



:HANDLE_DRIVER

ECHO Check driver ...

SET DRIVER_INF=%THIS_DIR%\lib\win\usb_device.inf
SET DRIVER_ID={eb781aaf-9c70-4523-a5df-642a87eca567}
SET DRIVER_KEY=HKLM\SYSTEM\CurrentControlSet\Control\Class\%DRIVER_ID%
REG QUERY "%DRIVER_KEY%\0000" /v "MatchingDeviceId" 1>NUL 2>NUL && GOTO:LOCATE_JAVA

ECHO Install driver ...

where pnputil 1>NUL 2>NUL    || GOTO:ERR_DRIVER
powershell -c "Start-Process pnputil -ArgumentList '/add-driver \"%DRIVER_INF%\" /install' -Wait -Verb RunAs"
pnputil /enum-drivers | find /i "%DRIVER_ID%" >NUL  || GOTO:ERR_DRIVER



:LOCATE_JAVA

ECHO Locate Java Runtime 8 ...

SET QUERY_JAVAHOME=REG QUERY "HKLM\SOFTWARE\JavaSoft\Java Runtime Environment\1.8" /v "JavaHome"
FOR /f "tokens=2*" %%a IN ('%QUERY_JAVAHOME% 2^>NUL ^| find "JavaHome"') DO SET "JAVA_HOME=%%~b"

SET QUERY_JAVAHOME=REG QUERY "HKLM\SOFTWARE\AdoptOpenJDK" /v Path /s
FOR /f "tokens=2*" %%a IN ('%QUERY_JAVAHOME% 2^>NUL ^| find "jre-8"') DO SET "JAVA_HOME=%%~b"

IF "%JAVA_HOME%" == "" GOTO:INSTALL_JAVA

SET JAVA=%JAVA_HOME%\bin\javaw.exe
IF EXIST "%JAVA%" GOTO:INSTALL_APP



:INSTALL_JAVA

SET JRE_FILE=%TEMP%\jre-8u221.exe

( ECHO INSTALL_SILENT=Enable
  ECHO STATIC=1
  ECHO AUTO_UPDATE=Disable
  ECHO WEB_JAVA=Disable
  ECHO WEB_ANALYTICS=Disable
  ECHO NOSTARTMENU=Enable
)>%JRE_FILE%.cfg

SET PS_DOWNLOAD_JAVA="(New-Object System.Net.WebClient).DownloadFile('%JRE_URL:"=%','%JRE_FILE:"=%');"
SET PS_INSTALL_JAVA="Start-Process -FilePath '%JRE_FILE%' -ArgumentList 'INSTALLCFG=\"%JRE_FILE%.cfg\"' -Wait -Verb RunAs;"

ECHO Downloading Java Runtime 8 ^(~80Mb, be patient^) ...
powershell -c %PS_DOWNLOAD_JAVA% || GOTO:ERR_INSTALL_JRE

ECHO Installing Java Runtime 8 ...
powershell -c %PS_INSTALL_JAVA% || GOTO:ERR_INSTALL_JRE

DEL "%JRE_FILE%" 2>&1 >nul
DEL "%JRE_FILE%.cfg" 2>&1 >nul

GOTO:LOCATE_JAVA



:INSTALL_APP

ECHO Install files ...

rmdir /S/Q "%PK_USRDIR%" >nul 2>&1

xcopy /Y/S/E "%THIS_DIR%\doc\*"                         "%PK_USRDIR%\doc\"      >NUL
xcopy /Y/S/E "%THIS_DIR%\fwr\*"                         "%PK_USRDIR%\fwr\"      >NUL
xcopy /Y/S/E "%THIS_DIR%\jar\*.jar"                     "%PK_USRDIR%\jar\"      >NUL
xcopy /Y/S/E "%THIS_DIR%\lib\win\%ARCH%\LibusbJava.dll" "%PK_USRDIR%\lib\"      >NUL
xcopy /Y/S/E "%THIS_DIR%\lib\win\%ARCH%\rxtxSerial.dll" "%PK_USRDIR%\lib\"      >NUL
xcopy /Y/S/E "%THIS_DIR%\lib\win\%ARCH%\msvcr100.dll"   "%PK_USRDIR%\lib\"      >NUL
copy  /Y     "%THIS_DIR%\ico\logo48.ico"                "%PK_USRDIR%\logo.ico"  >NUL

FOR /F %%f IN ('DIR /B/S "%PK_USRDIR%"') DO SET /A PK_INSTALLEDSIZE+=%%~zf/1024


ECHO Register Application ...

SET REG_KEY=HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\%PK_ID%

SET CMD_UNINSTALL=%ComSpec% /C^
  RMDIR /S/Q \"%PK_USRDIR%\" ^&^
  DEL /Q \"%PK_MENU_LINK%\" ^&^
  REG DELETE %REG_KEY% /f

REG ADD %REG_KEY% /f /v ProductID        /t REG_SZ     /d "%PK_ID"                >NUL
REG ADD %REG_KEY% /f /v DisplayIcon      /t REG_SZ     /d "%PK_USRDIR%\logo.ico"  >NUL
REG ADD %REG_KEY% /f /v DisplayName      /t REG_SZ     /d "%PK_NAME%"             >NUL
REG ADD %REG_KEY% /f /v DisplayVersion   /t REG_SZ     /d "%PK_VERSION%"          >NUL
REG ADD %REG_KEY% /f /v InstallLocation  /t REG_SZ     /d "%PK_USRDIR%"           >NUL
REG ADD %REG_KEY% /f /v UninstallString  /t REG_SZ     /d "%CMD_UNINSTALL%"       >NUL
REG ADD %REG_KEY% /f /v Publisher        /t REG_SZ     /d "%PK_PUBLISHER%"        >NUL
REG ADD %REG_KEY% /f /v HelpLink         /t REG_SZ     /d "%PK_HOMEPAGE%"         >NUL
REG ADD %REG_KEY% /f /v URLInfoAbout     /t REG_SZ     /d "%PK_HOMEPAGE%"         >NUL
REG ADD %REG_KEY% /f /v EstimatedSize    /t REG_DWORD  /d "%PK_INSTALLEDSIZE%"    >NUL
REG ADD %REG_KEY% /f /v NoModify         /t REG_DWORD  /d 1                       >NUL
REG ADD %REG_KEY% /f /v NoRepair         /t REG_DWORD  /d 1                       >NUL



ECHO Create menu shortcut ...

SET PS_CREATE_LINK=^
$lnk=(New-Object -COM WScript.Shell).CreateShortcut('%PK_MENU_LINK%');^
$lnk.TargetPath='%JAVA%';^
$lnk.Arguments='^
 -Djava.library.path=\"%PK_USRDIR%\lib\"^
 -Duser.dir=\"%PK_USRDIR%\etc\"^
 -cp \"%PK_USRDIR%\jar\*\"^
 \"com.owon.vds.tiny.Main\"';^
$lnk.IconLocation='%PK_USRDIR%\logo.ico,0';^
$lnk.Save();

DEL "%PK_MENU_LINK%" >nul 2>&1
powershell -c "%PS_CREATE_LINK%"



ECHO Done!

PAUSE & GOTO:EOF



:ERR_ARCHITECTURE
ECHO Error: platform not supported 1>&2
PAUSE & GOTO:EOF

:ERR_INSTALL_JRE
ECHO Error: failed to download/install Java Runtime 8 1>&2
ECHO   For a mannual intall: 1>&2
ECHO   https://www.java.com/en/download/manual.jsp 1>&2
PAUSE & GOTO:EOF

:ERR_POWERSHELL
ECHO Error: powershell not found 1>&2
PAUSE & GOTO:EOF

:ERR_DRIVER
ECHO Error: failed to install the driver 1>&2
ECHO   Try to install the driver manually via device manager 1>&2
ECHO   Driver location:  %THIS_DIR%\lib\win 1>&2
START "" /B devmgmt.msc
PAUSE & GOTO:EOF



REM :INSTALL_JAVA

REM SET JRE_FILE=%TEMP%\jre-setup.msi
REM SET JRE_URL="https://github.com/AdoptOpenJDK/openjdk8-binaries/releases/download/jdk8u222-b10_openj9-0.15.1/OpenJDK8U-jre_x64_windows_openj9_windowsXL_8u222b10_openj9-0.15.1.msi"
REM SET PS_SET_TLS="[Net.ServicePointManager]::SecurityProtocol='tls12,tls11,tls';"
REM SET PS_DOWNLOAD_JAVA="%PS_SET_TLS:"=%(New-Object System.Net.WebClient).DownloadFile('%JRE_URL:"=%','%JRE_FILE:"=%');"
REM SET PS_INSTALL_JAVA="Start-Process -FilePath msiexec -ArgumentList '/i \"%JRE_FILE%\" ADDLOCAL=FeatureMain,FeatureEnvironment /quiet' -Wait -Verb RunAs;"

REM FOR /F %%f in ("%JRE_FILE%") DO IF %%~zf LSS 40000000 (
	REM ECHO Downloading Java Runtime 8 ^(~40Mb, be patient^) ...
	REM powershell -c %PS_DOWNLOAD_JAVA% || GOTO:ERR_INSTALL_JRE
REM )
REM FOR /F %%f in ("%JRE_FILE%") DO IF %%~zf LSS 40000000 GOTO:ERR_INSTALL_JRE

REM ECHO Installing Java Runtime 8 ...
REM powershell -c %PS_INSTALL_JAVA% || GOTO:ERR_INSTALL_JRE

REM GOTO:LOCATE_JAVA

REM echo %PS_DOWNLOAD_JAVA%
REM echo %PS_INSTALL_JAVA%

REM goto:eof