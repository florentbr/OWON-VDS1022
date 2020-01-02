
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


It's based on the OWON Windows software for VDS1022/I 1.0.30 :  
http://files.owon.com.cn/software/pc/OWON_VDS_C2_Setup.zip  

Official website :  
http://www.owon.com.hk/products_owon_vds_series_pc_oscilloscope  

Unofficial release :  
https://github.com/florentbr/Owon-VDS1022/releases  



## Install

Open a terminal window in this folder and type:  

Linux   : `bash install-linux.sh`  
OSX     : `bash install-mac.sh`  
Windows : `install-win.cmd`  

On Linux, the script builds a package according to the platform and installs it with the default package manager.  
On Windows, the script copies the files to `C:\Program Files`, registers the app for uninstall and creates a menu entry.  
On Mac, the script simply copies the files to `/Applications`.  


## Dependencies

This software requires Java Runtime Environnement 8 or superior:

https://adoptopenjdk.net/  
https://openjdk.java.net/  
https://www.java.com/en/download/manual.jsp  
https://www.oracle.com/technetwork/java/javase/downloads/jre8-downloads-2133155.html  


## Calibration

The device can be calibrated either automatically (Home/Utility) or manually (F2).

If you wish to calibrate the device manually then:
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

2020/01/03 (1.0.30-cf7)

* added librairies for ARM hardware (linux)
* updated the code for Java 8 and supperior and improved installers
* improved the device stability (synchronised heartbeat, 1 job per command, deduplicated commands).
* added new set of icons
* improved dock layout and panes
* improved Save/Pin wave pane
* merged save image / export operation to a single button/dialog
* added buttons to change the color of the waves
* added shortcuts: save/restore the current settings, zoom switch, full screen
* added localized trigger status messages
* fixed window displayed under taskbar
* fixed single trigger triggered unexpectedly
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
