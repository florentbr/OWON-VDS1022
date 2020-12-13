#!/bin/bash

set -e
pushd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null

_ID='owon-vds-tiny'
_NAME='OWON VDS1022 Oscilloscope'
_VERSION=$(<./version.txt)
_VENDOR='Copyright (C) Fujian Lilliput Optoelectronics Technology Co.,Ltd'
_SUMMARY='Application for the OWON VDS1022 oscilloscope'
_ARCH=$(uname -m)


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


echo "==========================================================="
echo " Install '${_NAME}'                                        "
echo "==========================================================="

echo 'Check environement ...'

[ $EUID -eq 0           ] || raise "This script requires eleveted privileges."
[ -d "./lib/mac/$_ARCH" ] || raise "Architecture not supported: ${_ARCH}"
[ -d "/Applications"    ] || raise "Folder /Applications missing"


echo 'Locate Java Runtime ...'

JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null)
[ -d "$JAVA_HOME" ] || raise "Java not found. To install, visit adoptopenjdk.net"
printf "\n  JAVA_HOME : ${JAVA_HOME}\n\n"


echo 'Install application ...'

rm -rf "/Applications/$_NAME.app"

copy "/Applications/$_NAME.app/Contents/MacOS/" ./lib/mac/$_ARCH/*
copy "/Applications/$_NAME.app/Contents/Resources/" ./fwr ./jar ./doc ./version.txt
copy "/Applications/$_NAME.app/Contents/Resources/$_ID.icns" ./ico/icon48.icns

write "/Applications/$_NAME.app/Contents/MacOS/$_ID" +x <<-EOF
#!/bin/bash
/usr/libexec/java_home --exec java\\
 -Xdock:icon='/Applications/$_NAME.app/Contents/Resources/$_ID.icns'\\
 -XstartOnFirstThread\\
 -Djava.library.path='/Applications/$_NAME.app/Contents/MacOS'\\
 -Duser.dir="\$HOME/.$_ID"\\
 -cp '/Applications/$_NAME.app/Contents/Resources/jar/*'\\
 com.owon.vds.tiny.Main
EOF

write "/Applications/$_NAME.app/Contents/Info.plist" <<-EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>CFBundleDevelopmentRegion</key>        <string>English</string>
        <key>CFBundleExecutable</key>               <string>${_ID}</string>
        <key>CFBundleName</key>                     <string>${_NAME}</string>
        <key>CFBundleGetInfoString</key>            <string>${_SUMMARY}</string>
        <key>CFBundleIconFile</key>                 <string>${_ID}.icns</string>
        <key>CFBundleIdentifier</key>               <string>${_ID}</string>
        <key>CFBundleVersion</key>                  <string>${_VERSION}</string>
        <key>CFBundleShortVersionString</key>       <string>${_VERSION}</string>
        <key>CFBundleInfoDictionaryVersion</key>    <string>6.0</string>
        <key>CFBundlePackageType</key>              <string>APPL</string>
        <key>CSResourcesFileMapped</key>            <true/>
        <key>LSRequiresCarbon</key>                 <true/>
        <key>NSHumanReadableCopyright</key>         <string>${_VENDOR}</string>
        <key>NSPrincipalClass</key>                 <string>NSApplication</string>
        <key>NSHighResolutionCapable</key>          <true/>
    </dict>
</plist>
EOF


echo 'Clear previous settings ...'

rm -f /home/*/.$_ID/preferences*


printf "\nDone!\n"
