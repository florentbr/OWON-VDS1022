#!/bin/bash

if [[ $EUID -ne 0 ]] ;then
	echo "Error: This script requires eleveted privileges." >&2
	exit 1
fi

set -e

THIS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd) || exit 1
THIS_ARCH=$(uname -m) || exit 1

PK_VERSION=$(<$THIS_DIR/version.txt)
PK_VENDOR='Copyright (C) Fujian Lilliput Optoelectronics Technology Co.,Ltd'
PK_ID='owon-vds-tiny'
PK_NAME='OWON VDS1022 Oscilloscope'
PK_CATEGORIES='Electronics;Engineering'
PK_SUMMARY='Application for the OWON VDS1022 oscilloscope'
PK_CONTACT='florentbr@gmail.com'
PK_HOMEPAGE='https://github.com/florentbr/Owon-VDS1022'
PK_APP_DIR="/Applications/$PK_NAME.app"
PK_USER_DIR="\$HOME/.$PK_ID"
PK_DESCRIPTION='Unofficial release with a few improvements:
 * New shortcuts: single trigger, trigger level, offsets, coupling, inversion, reset ...
 * Disabled annoying dock animations
 * Disabled leave/stop confirmation while recording/playing'


main () {

	echo "==========================================================="
	echo " Install application '${PK_ID}'                                  "
	echo "==========================================================="
	echo 

	[ -d $THIS_DIR/lib/mac/$THIS_ARCH ] || raise "Architecture not supported: ${THIS_ARCH}"


	echo 'Locate Java Runtime ...'

	/usr/libexec/java_home &>/dev/null || {
		>&2 echo "Error: Java Runtime not found."
		>&2 echo "  To install, visit  adoptopenjdk.net  or java.com"
		return 1
	}

	printf "\nJAVA_HOME :\n  $(/usr/libexec/java_home)\n\n"


	echo 'Install application ...'

	rm -rf "$PK_USER_DIR/preferences*"
	rm -rf "$PK_APP_DIR"

	cpdir "$PK_APP_DIR/Contents/MacOS/"      "$THIS_DIR/lib/mac/$THIS_ARCH/lib"*
	cpdir "$PK_APP_DIR/Contents/Resources/"  "$THIS_DIR/fwr"
	cpdir "$PK_APP_DIR/Contents/Resources/"  "$THIS_DIR/doc"
	cpdir "$PK_APP_DIR/Contents/Resources/"  "$THIS_DIR/jar"

	cpfile "$PK_APP_DIR/Contents/Resources/$PK_ID.icns" "$THIS_DIR/ico/icon48.icns"
	cpfile "$PK_APP_DIR/Contents/Resources/version.txt" "$THIS_DIR/version.txt"

	write "$PK_APP_DIR/Contents/MacOS/$PK_ID" +x <<-EOF
	#!/bin/bash
	/usr/libexec/java_home --exec java \\
	  -Xdock:icon='$PK_APP_DIR/Contents/Resources/$PK_ID.icns' \\
	  -Djava.library.path='$PK_APP_DIR/Contents/MacOS' \\
	  -Duser.dir="$PK_USER_DIR" \\
	  -cp '$PK_APP_DIR/Contents/Resources/jar/*' \\
	  'com.owon.vds.tiny.Main'
	EOF

	write "$PK_APP_DIR/Contents/Info.plist" <<-EOF
	<?xml version="1.0" encoding="UTF-8"?>
	<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
	<plist version="1.0">
	<dict>
		<key>CFBundleDevelopmentRegion</key>        <string>English</string>
		<key>CFBundleExecutable</key>               <string>${PK_ID}</string>
		<key>CFBundleName</key>                     <string>${PK_NAME}</string>
		<key>CFBundleGetInfoString</key>            <string>${PK_SUMMARY}</string>
		<key>CFBundleIconFile</key>                 <string>${PK_ID}.icns</string>
		<key>CFBundleIdentifier</key>               <string>${PK_ID}</string>
		<key>CFBundleVersion</key>                  <string>${PK_VERSION}</string>
		<key>CFBundleShortVersionString</key>       <string>${PK_VERSION}</string>
		<key>CFBundleInfoDictionaryVersion</key>    <string>6.0</string>
		<key>CFBundlePackageType</key>              <string>APPL</string>
		<key>CSResourcesFileMapped</key>            <true/>
		<key>LSRequiresCarbon</key>                 <true/>
		<key>NSHumanReadableCopyright</key>         <string>${PK_VENDOR}</string>
		<key>NSPrincipalClass</key>                 <string>NSApplication</string>
		<key>NSHighResolutionCapable</key>          <true/>
	</dict>
	</plist>
	EOF

	printf "\nBINARY:\n  $PK_APP_DIR/Contents/MacOS/$PK_ID \n"

	printf "\nDone!\n"
}


cpdir () {
	mkdir -p "$1"
	cp --no-preserve=mode,ownership -r "${@:2}" "$1"
}

cpfile () {
	mkdir -p "$(dirname "$1")"
	cp --no-preserve=mode,ownership "$2" "$1"
}

write () {
	mkdir -p "$(dirname "$1")"
	echo -e "$(cat -)" > "$1"
	[ -z "$2" ] || chmod "$2" "$1"
}

raise () {
	printf "\nError: $1\n" >&2
	exit 1
}


main "$@"
