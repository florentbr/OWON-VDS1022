#!/bin/bash

set -e
pushd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null

_ID='owon-vds-tiny'
_NAME='OWON VDS1022'
_FULLNAME='OWON VDS1022 Oscilloscope'
_VENDOR='Copyright (C) Fujian Lilliput Optoelectronics Technology Co.,Ltd'
_SUMMARY='Application for the OWON VDS1022 oscilloscope'
_HOMEPAGE='https://github.com/florentbr/OWON-VDS1022'
_VERSION=$(<./version.txt)
_ARCH=$(uname -m)


write () {
    echo -e "$(</dev/stdin)" > "$1"
    [ -z "$2" ] || chmod "$2" "$1"
}

raise () {
    printf "Error: $1\n\n" >&2
    exit 1
}


echo "==========================================================="
echo " Install ${_NAME} ${_VERSION}                              "
echo " ${_HOMEPAGE}                                              "
echo "==========================================================="


echo "Check environement ..."

[ $EUID -eq 0 ] || raise "This script requires eleveted privileges."
[ -d /Applications ] || raise "Folder /Applications missing"
[ -d lib/mac/$_ARCH ] || raise "Architecture not supported: ${_ARCH}"


echo "Locate Java Runtime ..."

JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null || true)
[ -d "$JAVA_HOME" ] || raise "Java not installed."
echo "$JAVA_HOME"


echo "Install to /Applications/$_NAME.app ..."

rm -fr "/Applications/$_NAME"*.app
mkdir -p "/Applications/$_NAME.app/Contents"/{MacOS,Resources}
mkdir -p "/Applications/$_NAME.app/Contents"/Resources/{api,doc,fwr,lib}

cp version.txt             "/Applications/$_NAME.app/Contents/Resources/"
cp ico/icon.icns           "/Applications/$_NAME.app/Contents/Resources/"
cp fwr/*.bin               "/Applications/$_NAME.app/Contents/Resources/fwr/"
cp lib/*.jar               "/Applications/$_NAME.app/Contents/Resources/lib/"
cp lib/mac/$_ARCH/*.dylib  "/Applications/$_NAME.app/Contents/Resources/lib/"
cp -r doc/*                "/Applications/$_NAME.app/Contents/Resources/doc/"

write "/Applications/$_NAME.app/Contents/MacOS/launch" +x <<EOF
#!/bin/bash
cd '/Applications/$_NAME.app/Contents/Resources'
/usr/libexec/java_home --exec java -Xdock:name='$_NAME' -Xdock:icon=icon.icns -cp 'lib/*' com.owon.vds.tiny.Main
EOF

write "/Applications/$_NAME.app/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>CFBundleIdentifier</key>             <string>${_ID}</string>
        <key>CFBundleDisplayName</key>            <string>${_FULLNAME}</string>
        <key>CFBundleName</key>                   <string>${_FULLNAME}</string>
        <key>CFBundleGetInfoString</key>          <string>${_SUMMARY}</string>
        <key>CFBundleVersion</key>                <string>${_VERSION}</string>
        <key>CFBundleShortVersionString</key>     <string>${_VERSION}</string>
        <key>CFBundleExecutable</key>             <string>launch</string>
        <key>CFBundleIconFile</key>               <string>icon.icns</string>
        <key>CFBundleDevelopmentRegion</key>      <string>English</string>
        <key>CFBundleInfoDictionaryVersion</key>  <string>6.0</string>
        <key>CFBundlePackageType</key>            <string>APPL</string>
        <key>CSResourcesFileMapped</key>          <true/>
        <key>LSRequiresCarbon</key>               <true/>
        <key>NSHumanReadableCopyright</key>       <string>${_VENDOR}</string>
        <key>NSPrincipalClass</key>               <string>NSApplication</string>
        <key>NSHighResolutionCapable</key>        <true/>
    </dict>
</plist>
EOF


echo 'Initialize "~/Library/Application Support/OWON VDS1022" ...'

rm -fr /Users/*/.owon-vds-tiny
rm -f /Users/*/"Library/Application Support/$_NAME"/preferences*


printf "\nSUCCESS !\n"
