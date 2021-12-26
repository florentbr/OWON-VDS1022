
### Java

from http://files.owon.com.cn/software/pc/OWON_VDS_C2_Setup.zip :  
 * OWON_VDS_C2_1.0.X_Setup.exe\plugins\com.owon.vds.tiny_1.0.X.jar  
 * OWON_VDS_C2_1.0.X_Setup.exe\plugins\com.owon.vds.foundation_1.0.0.jar  
from https://sourceforge.net/projects/libusbjava/files/libusbjava-snapshots/20090517 :  
 * ch.ntb.usb-0.5.9.jar  
from https://github.com/google/gson :  
 * gson-2.7.0.jar  
from http://jexcelapi.sourceforge.net :  
 * jxl-2.6.6.jar  

The files "com.owon.vds.tiny_1.0.X.jar" and "com.owon.vds.foundation_1.0.0.jar" were 
merged to a single JAR named "owon-vds-tiny-1.0.X-cfx.jar" .  

The class "LibusbJava.java" in "ch.ntb.usb-0.5.9.jar" was modified to first try to load the 
native dependency libusbJava from the same folder if present. The source is included in the jar.  

The original code was decompiled with JD-GUI :  
http://java-decompiler.github.io  


### FPGA Firmware

from http://files.owon.com.cn/software/pc/OWON_VDS_C2_Setup.zip :  
 * OWON_VDS_C2_1.0.X_Setup.exe\fpga\vds1022\VDS1022_FPGAV1_VX.X.bin  
 * OWON_VDS_C2_1.0.X_Setup.exe\fpga\vds1022\VDS1022_FPGAV2_VX.X.bin  
 * OWON_VDS_C2_1.0.X_Setup.exe\fpga\vds1022\VDS1022_FPGAV3_VX.X.bin  


### Native Windows / libusb 0.1 / Microsoft C Runtime 2010

from http://files.owon.com.cn/software/pc/OWON_VDS_C2_Setup.zip :  
 * USBDRV\win10_win8_win7_vista\*  
from https://sourceforge.net/projects/libusbjava/files/libusbjava-snapshots/20090517 :  
 * LibusbJava.dll  
from Microsoft Visual C++ 2010 Redistributable :  
 * msvcr100.dll  
 * msvcp100.dll  

sources:  
https://sourceforge.net/p/libusbjava/code/HEAD/tree/branches/libusb_api_0v1/LibusbJava/  
https://www.catalog.update.microsoft.com/Search.aspx?q=C%2B%2B%202010%20Redistributable  


## Native Linux / libusbJava 0.1

from https://packages.debian.org/sid/libusb-java-lib :  
 * libusbJava.so.0.8  
from https://pkgs.org/download/libusb-compat :  
 * libusb-0.1.so.4.4.4  

Renamed library 'libusbJava.so.0.8' to 'libusbJava.so'  
Renamed library 'libusb-0.1.so.4.4.4' to 'libusb-0.1.so.4'  
in 'libusbJava.so', changed soname [libusbJavaSh.so] to [libusbJava.so]  
in 'libusbJava.so', added `rpath=$ORIGIN` to resolve libusb-0.1.so.4 in the same folder  

sources:  
https://sourceforge.net/p/libusbjava/code/HEAD/tree/branches/libusb_api_0v1/LibusbJava/  
https://sourceforge.net/projects/libusb/files/libusb-compat-0.1/  
https://github.com/freecores/usb_fpga_1_2/tree/master/libusbJava-src  

linking:  
https://github.com/NixOS/patchelf  
https://amir.rachum.com/blog/2016/09/17/shared-libraries  


## Native Mac OS / libusbJava 0.1

from https://formulae.brew.sh/formula/libusb-compat :  
 * libusb-0.1.4.dylib  
from https://formulae.brew.sh/formula/libusb :  
 * libusb-1.0.0.dylib  
from https://salsa.debian.org/java-team/libusb-java :
 * libusbJava.dylib

Linked paths were all changed to `@loader_path` via `rpath`  

sources:  
https://sourceforge.net/p/libusbjava/code/HEAD/tree/branches/libusb_api_0v1/LibusbJava/  
https://salsa.debian.org/java-team/libusb-java  
https://sourceforge.net/projects/libusb/files/libusb-compat-0.1/  

linking:  
https://www.unix.com/man-page/osx/1/install_name_tool/  
https://matthew-brett.github.io/docosx/mac_runtime_link.html  
https://pavelevstigneev.medium.com/making-portable-binary-for-macos-52ff4f827fbd
