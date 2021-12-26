
# OWON VDS1022/I Oscilloscope

This software is an unofficial release for the VDS1022 with a few improvements :

* Scripts to install the app on Linux/Windows/Mac
* A Python API to directly communicate with the device to log, analyse and plot
* New shortcuts: single trigger, trigger level, offsets, coupling, inversion, reset ...
* Added single/normal triggering for the rolling mode (time base >= 100ms/div)
* Added a vertical mark cursor to adjust the pulse/slope trigger width
* Added a vertical mark cursor to measure the duty cycle and phase angle
* Added measures for the Math channel
* Added an option to measure a current instead of a voltage
* Added buttons to change the color of the waves
* Added buttons to store/restore the current settings while keeping the same calibration
* Added a x20, x50 and x500 probe ratio
* Improved the device stability and interface
* Disabled the leave/stop confirmation while recording/playing
* Merged the save image / export operation to a single button/dialog
* Many fixes (see [change list](changes.txt))


This software is based on the OWON release for the VDS1022(I) 1.1.1 :  
http://www.owon.com.hk/products_owon_vds_series_pc_oscilloscope  

This device is also sold under different brands:
* Multicomp Pro MP720016 / MP720017
* PeakTech 1290


## Requirements

Java Runtime Environement 8 (1.8) or superior is required. Java 11 is recommended especially if you have an HDPI display.  
To check if Java is installed with the minimum version, run `java -version` in a console.  
Installers are available at https://adoptopenjdk.net/releases.html (OpenJDK 11 JRE ~50Mb).  
It should work just fine on any computer/laptop as long as there's 200Mb of free RAM.  


## Install

Download and extract the latest release :  

https://github.com/florentbr/OWON-VDS1022/tags  

#### Windows 10, 8, 7, XP (x86/amd64)

Right click on `install-win.cmd` and select "Run as administrator".  

The script installs the driver, copies the files, registers for uninstall and creates a menu entry.  
User settings are stored in `%APPDATA%\OWON VDS1022`.  

To debug, run `%PROGRAMFILES%\OWON VDS1022\launch.cmd`.  
To fully uninstall, open your application manager and select "OWON VDS1022"  

#### Linux (Debian based, Arch based, Puppy, Fedora ...)

Open a terminal window in this folder and execute `sudo bash install-linux.sh` .  

The script builds a package according to the distribution and installs it with the default package manager.  
User settings are stored in `$HOME/.owon-vds-tiny` once the application is launched.  

To debug, run `owon-vds-tiny` from a console.  
To fully uninstall, open your application manager and select "owon-vds-tiny" or "OWON VDS1022"  

#### macOS (64 bits Intel and ARM Apple silicon)

Open a terminal window in this folder and execute `sudo bash install-mac.sh` .  

The script simply writes the files into `/Applications/OWON VDS1022` .  
User settings are stored in `~/Library/Application Support/OWON VDS1022`.  
To debug, run `/Applications/OWON VDS1022.app/Contents/MacOS/launch` from a console.  
To fully uninstall, delete `/Applications/OWON VDS1022` and `~/Library/Application Support/OWON VDS1022`  


## Calibration

The device can be calibrated either automatically (Home/Utility/Auto-Calibrate) or manually (F2).
The Auto-Calibrate adjusts the zero offset/amplitude but not the gain since it requires a reference voltage.

If you wish to calibrate the device manually then:
* Disconnect the probes
* Press F2 to open the calibration dialog
* Select the Zero compensation tab
* For each voltage, adjust the calibration as to obtain a 0v signal
* Select the Zero amplitude tab
* For each voltage, adjust the calibration as to obtain a 0v signal
* Select the Gain tab
* For each voltage, connect the probe to a reference voltage and adjust the calibration

The factory calibration is stored directly in the device in the flash memory.  
The current calibration is stored in the user folder as "VDS1022xxxxxx-cals.json".  

## API

This project provides a Python API to directly communicate with the device.  
It can be used for data logging or to analyse and visualise the samples in a [Jupyter Notebook](https://jupyter.org/).  
The code and examples are available in the [api folder](api/).  

Simple measure :

```python
from vds1022 import *

dev = VDS1022()
dev.set_timerange('20ms')
dev.set_channel(CH1, range='50v', coupling='DC', offset='0v', probe='x10')

for ch1, ch2 in dev.pull_iter(freq=1, autorange=True) :
    print('rms:%s' % ch1.rms())
```

Plotting in a Jupyter notebook:

```python
from vds1022 import *

dev = VDS1022(debug=False)
dev.set_timerange('5ms')
dev.set_channel(CH1, range='10v', coupling=DC, offset=0, probe='x10')
dev.set_channel(CH2, range='10v', coupling=DC, offset=0, probe='x10')
dev.set_trigger(CH1, EDGE, RISE, position=0.5, level='2.5v', sweep=ONCE)
frames = dev.pull()
frames.plot()
```

![jupyter-plot](https://user-images.githubusercontent.com/918557/147412836-92f8b244-b0de-4b86-abb7-e431406660e2.png)


## SCPI Protocol

This device supports the SCPI protocol once the application is lauched and running.  
The server is off by default. Go to Utility to enable it.  

## Safety

This scope can measure 40v peak to peak with a 1x probe and 400v with a 10x probe.  
The max input voltage is 40v for the VDS1022 and 400v for the isolated version (VDS1022i).  

Since 230v AC RMS is 650v peak to peak, you can't analyse the main with a 10x probe.  
To safely probe the main, use a 100x probe and only connect the ground of the probes to ground/earth.  
To safely probe between two potentials, even if it's a Neutral, either use two probes and substract the waves (Math menu) or use a differential probe.  

You shouldn't connect the ground of the probe to a potential unless you know exacly what you are doing. You'll have to make sure that it doesn't loop back to the main ground/earth thought the computer power supply if connected. Also, check that it's properly isolated from your oscilloscope and computer/laptop case if the applied voltage is not safe. It should be the case with the isolated version (VDS1022i). Be also aware that the channels have a common ground which would create a short if connected to two different voltages. If you want to know more on the subject, search for "ground loop oscilloscope" and "earthing system".

## Changes

See [changes.txt](changes.txt)

## Donation

If you like it and want to support its development, you can buy me a beer.

[![paypal](https://www.paypalobjects.com/en_US/FR/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/donate/?cmd=_donations&business=7DUHBU9VETYXE)
