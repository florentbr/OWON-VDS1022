
# OWON VDS1022/I Oscilloscope

This software is an unofficial release for the OWON VDS oscilloscope with a few improvements:

* Scripts to install the app on Linux/Windows/Mac
* New shortcuts: single trigger, trigger level, offsets, coupling, inversion, reset ...
* Disabled anoying dock animations
* Disabled leave/stop confirmation while recording/playing


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



## Dependencies

This software depends on Java Runtime Environnement 8. Due to the use of a deprecated api, the app won't run on Java 9 and superior. The installer will install the required version. In case it fails, you can try to install it manually:  

https://openjdk.java.net/  
https://adoptopenjdk.net/  
https://www.java.com/en/download/manual.jsp  



## Changes

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
