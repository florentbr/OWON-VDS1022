#!/bin/bash

set -e
pushd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null

ARCH=$(uname -m)

PK_VERSION=$(<./version.txt)
PK_VENDOR='Copyright (C) Fujian Lilliput Optoelectronics Technology Co.,Ltd'
PK_ID='owon-vds-tiny'
PK_NAME='OWON VDS1022 Oscilloscope'
PK_CATEGORIES='Electronics;Engineering'
PK_SUMMARY='Application for the OWON VDS1022 oscilloscope'
PK_CONTACT='florentbr@gmail.com'
PK_HOMEPAGE='https://github.com/florentbr/Owon-VDS1022'
PK_APP_DIR="/Applications/$PK_NAME.app"


main () {

	[ $EUID -eq 0 ] || raise "This script requires eleveted privileges."
	[ -d "./lib/mac/$ARCH" ] || raise "Architecture not supported: ${ARCH}"
	[ -d "/Applications" ] || raise "Folder /Applications missing"


	echo "==========================================================="
	echo " Install application '${PK_NAME}'                          "
	echo "==========================================================="

	echo 'Locate Java Runtime ...'

	local JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null)
	[ -d "$JAVA_HOME" ] || raise "Java not found. To install, visit adoptopenjdk.net or java.com"
	printf "\n  JAVA_HOME : ${JAVA_HOME}\n\n"


	echo 'Install application ...'

	rm -rf "$PK_APP_DIR"

	copy "$PK_APP_DIR/Contents/MacOS/"                ./lib/mac/$ARCH/*
	copy "$PK_APP_DIR/Contents/Resources/"            ./fwr ./jar ./doc ./version.txt
	copy "$PK_APP_DIR/Contents/Resources/$PK_ID.icns" ./ico/icon48.icns

	write "$PK_APP_DIR/Contents/MacOS/$PK_ID" +x <<-EOF
	#!/bin/bash
	/usr/libexec/java_home --exec java\\
	 -Xdock:icon='$PK_APP_DIR/Contents/Resources/$PK_ID.icns'\\
	 -Djava.library.path='$PK_APP_DIR/Contents/MacOS'\\
	 -Duser.dir="\$HOME/.$PK_ID"\\
	 -cp '$PK_APP_DIR/Contents/Resources/jar/*'\\
	 com.owon.vds.tiny.Main
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


	echo 'Clear previous settings ...'

	rm -f /home/*/.$PK_ID/preferences*


	printf "\nDone!\n"
}


copy () {
	if [[ "$1" == */ ]] || [[ -d "$1" ]] ; then
		mkdir -p "$1"
		cp -r "${@:2}" "$1"
	else
		mkdir -p "$(dirname "$1")"
		cp "${@:2}" "$1"
	fi
}

write () {
	mkdir -p "$(dirname "$1")"
	echo -e "$(cat -)" > "$1"
	[ -z "$2" ] || chmod "$2" "$1"
}

raise () {
	printf "Error: $1\n\n" >&2
	exit 1
}


main "$@"
