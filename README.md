
# OWON VDS1022/I Oscilloscope

This software is an unofficial release for the OWON VDS oscilloscope with a few improvements:

* Scripts to install the app on Linux/Windows/Mac
* New shortcuts: single trigger, trigger level, offsets, coupling, inversion, reset ...
* Added buttons to change the color of the waves
* Improved the dock layout and disabled animations
* Improved the device stability
* Disabled the leave/stop confirmation while recording/playing
* Merged the save image / export operation to a single button/dialog
* Many fixes (see change list)


This software is based on the OWON release for VDS1022/I 1.0.30 :  
http://files.owon.com.cn/software/pc/OWON_VDS_C2_Setup.zip  

Official website :  
http://www.owon.com.hk/products_owon_vds_series_pc_oscilloscope  


## Dependencies

This software requires Java Runtime Environnement 8 or superior:

https://adoptopenjdk.net/  
https://openjdk.java.net/  
https://www.java.com/en/download/manual.jsp  
https://www.oracle.com/technetwork/java/javase/downloads/jre8-downloads-2133155.html  


## Install

Download and extract the latest release :  

https://github.com/florentbr/OWON-VDS1022/releases  

#### Windows 10, 8, 7, XP

Right click on `install-win.cmd` and select "Run as administrator".  

The script installs the drivers, copies the files, registers for uninstall and creates a menu entry.  
User settings are stored in `%APPDATA%\OwonVdsTiny`  once the application is launched.

If the shortcut "OWON VDS1022 Oscilloscope" is not visible in the Windows menu, then restart your machine.  

#### Linux

Open a terminal window and execute `sudo bash install-linux.sh` .  
  
The script builds a package according to the distribution and installs it with the default package manager.  
User settings are stored in `$HOME/.owon-vds-tiny`  once the application is launched.

#### OSX

Open a terminal window and execute `sudo bash install-mac.sh` .  

The script simply creates/copies the files into `/Applications` .  
User settings are stored in `$HOME/.owon-vds-tiny`  once the application is launched.


## Calibration

The device can be calibrated either automatically (Home/Utility/Auto-Calibrate) or manually (F2).

If you wish to calibrate the device manually then:
* Press F2 to open the calibration dialog
* Disconnect the probes
* Select a x1 ratio and a DC coupling for each probe 
* Select the targeted voltage to calibrate
* Move the voltage offset to 0 volts
* Adjust the Zero compensation to align the signal with the cursor
* Move the voltage offset to the top
* Adjust the Zero amplitude to align the signal with the cursor
* Connect the probe to a reference voltage
* Adjust the Coarse Gain until the signal has the expected amplitude

The factory calibration is stored directly in the device.  
The current calibration is stored in the user folder.  


## Changes

2020/12/13 (1.0.33-cf11)
* added shortcut for normal sweep
* fixed russian translation (thanks to LeonIndman)
* fixed and improved file export (text, csv, xls)
* fixes from update 1.0.33 (FFT Hz/Div, chartscreen clipping)
* removed factory flash part from update 1.0.33
* improved/fixed install scripts (files permissions for Linux)

2020/06/10 (1.0.30-cf10)
* added Italian translation (thanks to Marco Morelli)
* changed channel 1 factory color from red to green
* changed default factory coupling from AC to DC
* changed retore button to restore the saved settings instead of the factory settings
* fixed trigger pulse/slope input width
* removed unsupported install USB driver menu
* improved/fixed install scripts (issues 4, 7, 8)

2020/01/17 (1.0.30-cf9)
* fixed horizontal zoom when stopped

2020/01/13 (1.0.30-cf8)
* fixed combobox popups disapearing once clicked (Windows)
* improved install scripts

2020/01/03 (1.0.30-cf7)

* added librairies for ARM hardware (linux)
* improved device stability (synchronised heartbeat, 1 job per command, deduplicated commands)
* added new set of icons
* improved dock layout and panes
* improved Save/Pin wave pane
* improved manual calibration dialog (F2)
* merged save image / export operation to a single button/dialog
* added buttons to change the color of the waves
* added shortcuts: save/restore the current settings, zoom switch, full screen
* added localized trigger status messages
* fixed the code to support Java 8 and superior (Java 6 no longer supported)
* fixed install scripts
* fixed window size/position at startup
* fixed single trigger triggered unexpectedly once initiated
* fixed math/composite auto-set voltage
* fixed scaling of the view (3 views / print preview)
* fixed focus issues with dialogs/sliders
* fixed mouse gesture labels

2019/10/19

* added support to Puppy Linux
* fixed unsupported translucency by some OS
* fixed reset operation on sliders
* fixed english translation in the calibration dialog and re-factored load/export

2019/09/23

* fixed swallowed exception Assistive Technology not found
* added missing window title
* added shortcuts: single trigger, trigger level, offsets, coupling, inversion, reset ...
* changed trigger limit to 200ms
* fixed the voltage division not refreshed when changed via shortcut and not running
* moved tune file to user folder
* moved deep memory file to temp folder
* moved reference wave files to user folder
* moved default play/record file to user folder
* moved calibration to user folder
* moved settings to user folder
* moved preferences to user folder
* disabled leave/stop confirmation while playing
* disabled debug log by default
* disabled the SCPI server by default
* disabled dock animations
* fixed help and tips
* fixed the save image operation - forced default filter to PNG
* fixed the marks container appearing as a second window in the task-bar
* fixed notice dialog leading to a deadlock when the device is connected
* moved FPGA files to fwr
* fixed system properties
* added option to change the application folder via property
* fixed the exception "LibusbJava.usb_set_configuration: Could not set config 1". Removed the unnecessary call to `usb_set_configuration`
