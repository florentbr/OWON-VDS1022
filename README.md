
# OWON VDS1022/I Oscilloscope

This software is an unofficial release for the OWON VDS oscilloscope with a few improvements:

* Scripts to install the app on Linux/Windows/Mac
* New shortcuts: single trigger, trigger level, offsets, coupling, inversion, reset ...
* Added single/normal triggering for the rolling mode (time base >= 100ms/div)
* Added option to measure a current instead of a voltage
* Added buttons to change the color of the waves
* Added option to persist/restore the settings
* Improved the device stability and reduced CPU footprint
* Improved the dock layout and disabled animations
* Disabled the leave/stop confirmation while recording/playing
* Merged the save image / export operation to a single button/dialog
* Many fixes (see [change list](changes.txt))


This software is based on the OWON release for the VDS1022(I) 1.0.33 :  
http://www.owon.com.hk/products_owon_vds_series_pc_oscilloscope  

Note that this oscilloscope is also sold under different brands:
* [PeakTech 1290](https://www.peaktech.de/productdetail/kategorie/pc-oszilloskope/produkt/p_1290.html)
* [Multicomp Pro MP720017](https://uk.farnell.com/multicomp-pro/mp720017-eu-uk/pc-oscilloscope-2-1-ch-25mhz-100msps/dp/3107576)


## Requirements

It requires Java Runtime Environnement 8 (1.8) or superior.  
To check if Java is correctly installed with the minimum version, run `java -version` in a console.  
I recommend the installer from https://adoptopenjdk.net or https://www.java.com if Java is not already installed on your system.  

It should work just fine on any computer/laptop as long as there's 200Mo of free RAM. I used it without any issue on an old HP nx7000 laptop from 2005.  

## Install

Download and extract the latest release :  

https://github.com/florentbr/OWON-VDS1022/releases  

#### Windows 10, 8, 7, XP (32/64bits)

Right click on `install-win.cmd` and select "Run as administrator".  

The script installs the driver, copies the files, registers for uninstall and creates a menu entry.  
User settings are stored in `%APPDATA%\OwonVdsTiny` once the application is launched.

If the shortcut "OWON VDS1022 Oscilloscope" is not visible in the Windows menu or if the application doesn't launch, then try to restart your machine.  

To look at the debug info, run `C:\Program Files\OwonVdsTiny\launch.cmd`.  

#### Linux (Debian based, Arch based, Puppy, Fedora ..)

Open a terminal window in this folder and execute `sudo bash install-linux.sh` .  

The script builds a package according to the distribution and installs it with the default package manager.  
User settings are stored in `$HOME/.owon-vds-tiny` once the application is launched.

To look at the debug info, run `owon-vds-tiny` from a console.  

#### OSX (64 bits only)

Open a terminal window in this folder and execute `sudo bash install-mac.sh` .  

The script simply writes the files into `/Applications/OWON VDS1022 Oscilloscope` .  
User settings are stored in `$HOME/.owon-vds-tiny` once the application is launched.

To look at the debug info, run `/Applications/OWON VDS1022 Oscilloscope.app/Contents/MacOS/owon-vds-tiny` from a console.  

## Calibration

The device can be calibrated either automatically (Home/Utility/Auto-Calibrate) or manually (F2).

If you wish to calibrate the device manually then:
* Disconnect the probes
* Select a x1 ratio and a DC coupling for each probe 
* Press F2 to open the calibration dialog
* Select the targeted voltage to calibrate
* Move the voltage offset to 0 volts
* Adjust the Zero compensation to align the signal with the cursor
* Move the voltage offset to the top
* Adjust the Zero amplitude to align the signal with the cursor
* Connect the probe to a reference voltage
* Adjust the Coarse Gain until the signal has the expected amplitude

The factory calibration is stored directly in the device.  
The current calibration is stored in the user folder.  

Note that the accuracy of this scope seems to rely on the accuracy of the 5v from the power supply provided by the USB port.  

## Safety

This scope can measure 40v peak to peak with a 1x probe and 400v with a 10x probe.  
Since 230v AC RMS is 650v peak to peak, you can't analyse the main with a 10x probe.
To safely probe the main, use a 100x probe and only connect the ground of the probes to ground/earth.
To probe between two potentials, even if it's a Neutral, either use two probes and substrat the waves or use a differential probe.

If you plan to connect the ground of the probe to a potential (which I don't recommend), you'll have to make sure that it doesn't loop back to the main ground/earth and that it's properly isolated from your oscilloscope and computer/laptop case. Keep in mind that a mistake will put your life in danger and will likely destroy your equipment. If you want to know more on the subject, search for "ground loop oscilloscope" and "earthing system".

## Changes

See [changes.txt](changes.txt)

## Donation

If you like it and want to support its development, you can buy me a beer.

[![paypal](https://www.paypalobjects.com/en_US/FR/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/donate/?cmd=_donations&business=7DUHBU9VETYXE)
