#!/bin/bash

set -e
pushd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null

_SRCDIR=$(pwd)
_TMPDIR=$(readlink -f /tmp)

_ID='owon-vds-tiny'
_NAME='OWON VDS1022'
_FULLNAME='OWON VDS1022 Oscilloscope'
_GENERICNAME='Oscilloscope'
_SUMMARY='Application for the OWON VDS1022 oscilloscope'
_VERSION=$(<version.txt)
_VENDOR='Copyright (C) Fujian Lilliput Optoelectronics Technology Co.,Ltd'
_CATEGORIES='Utility;Electronics;Engineering'
_HOMEPAGE='https://github.com/florentbr/OWON-VDS1022'
_DESCRIPTION='Modified software for the OWON VDS1022 oscilloscope'


_PREINSTALL="
true
"
_POSTINSTALL="
rm -f /home/*/.$_ID/preferences* || true
udevadm control --reload-rules
udevadm trigger
"
_POSTREMOVE="
rm -fr /home/*/.$_ID || true
"


main () {

	[ "$EUID" = 0 ] || raise "This script requires eleveted privileges."

	echo "==========================================================="
	echo " Build package                                             "
	echo "==========================================================="

	echo 'Check environement ...'

	local arch=$(dpkg --print-architecture 2>/dev/null || uname -m)
	case "$arch" in
		amd64|x86_64)   arch=amd64 ;;
		arm64|aarch64*) arch=arm64 ;;
		i?86)           arch=i386  ;;
	esac
	[ -d "$_SRCDIR/lib/linux/$arch" ] || raise "Architecture not supported: ${arch}"


	local packager
	for packager in apt pacman dnf yum zypper ppm / ; do
		[ $packager = / ] && raise 'Package manager not supported'
		command -v $packager >/dev/null && break
	done

	local tmpdir=$(mktemp -d)
	pushd "$tmpdir" >/dev/null
	chmod 0755 .

	case $packager in
		apt)             build-deb $arch ;;
		pacman)          build-pac $arch ;;
		dnf|zipper|yum)  build-rpm $arch ;;
		ppm)             build-pet $arch ;;
	esac

	popd >/dev/null
	rm -rf "${tmpdir}"

	chmod 0755 "$_PACKAGE"
	printf "\nPackage:\n ${_PACKAGE}\n\n"


	echo "==========================================================="
	echo " Install package ${_PACKAGE##*/}                           "
	echo "==========================================================="

	case "$packager" in
		apt)     apt install --reinstall "$_PACKAGE" ;;
		pacman)  pacman -U "$_PACKAGE"               ;;
		dnf)     dnf install "$_PACKAGE"             ;;
		zipper)  zipper install "$_PACKAGE"          ;;
		yum)     yum install "$_PACKAGE"             ;;
		ppm)     pkg -f install "$_PACKAGE"          ;;
		*)       raise "Packager not supported"      ;;
	esac

	env -i /bin/bash -c 'type java >/dev/null 2>&1' || raise "Java not found!"

	echo -e "\nSUCCESS !\n"

}


build-deb () {
	local arch=$1

	write_files "$arch"

	local size=$(du -s -k | egrep -o '^[0-9]+')

	echo 'Build debian package ...'

	write DEBIAN/control <<EOF
Package: ${_ID}
Source: ${_ID}
Version: ${_VERSION}
Section: non-free/electronics
Depends: libusb-1.0-0, libc6, java-runtime
Architecture: ${arch}
Vendor: ${_VENDOR}
Installed-Size: ${size}
Maintainer: na <na>
Homepage: ${_HOMEPAGE}
Description: ${_SUMMARY}
 ${_DESCRIPTION}
EOF

	write DEBIAN/preinst +x <<EOF
#!/bin/bash
${_PREINSTALL}
EOF

	write DEBIAN/postinst +x <<EOF
#!/bin/bash
[ "\$1" = configure ] || exit 0
${_POSTINSTALL}
EOF

	write DEBIAN/postrm +x <<EOF
#!/bin/bash
[ "\$1" = remove ] || exit 0
${_POSTREMOVE}
EOF

	_PACKAGE="$_TMPDIR/$_ID-$_VERSION.$arch.deb"
	rm -f "$_PACKAGE"
	dpkg-deb -b -Zgzip . "$_PACKAGE" >/dev/null || exit 1
}


build-pac () {
	local arch=$1

	write_files "$arch"

	local size=$(du -s -b | egrep -o '^[0-9]+')

	case "$arch" in
		amd64|x86_64)   arch=x86_64  ;;
		arm64|aarch64*) arch=aarch64 ;;
	esac

	echo 'Build pacman package ...'

	write .PKGINFO +x <<EOF
pkgname = ${_ID}
pkgbase = ${_ID}
pkgver = ${_VERSION}
pkgdesc = ${_SUMMARY}
url = ${_HOMEPAGE}
builddate = $(date -u '+%s')
packager = na <na>
size = ${size}
arch = ${arch}
depend = libusb
depend = java-runtime
EOF

	write .INSTALL +x <<EOF
pre_install () {${_PREINSTALL}}
pre_upgrade () {${_PREINSTALL}}
post_install () {${_POSTINSTALL}}
post_upgrade () {${_POSTINSTALL}}
post_remove () {${_POSTREMOVE}}
EOF

	_PACKAGE="$_TMPDIR/$_ID-$_VERSION.$arch.pac"
	rm -f "$_PACKAGE"
	tar -czvf "$_PACKAGE" .PKGINFO .INSTALL * >/dev/null || exit 1
}


build-rpm () {
	local arch=$1

	mkdir BUILD BUILDROOT RPMS SOURCES SPECS SRPMS
	pushd BUILDROOT >/dev/null

	write_files "$arch"

	local files=$(find -type f | egrep -o '/.*')

	case "$arch" in
		amd64|x86_64)   arch=x86_64  ;;
		arm64|aarch64*) arch=aarch64 ;;
	esac

	popd >/dev/null

	echo 'Build rpm package ...'

	write "SPECS/$_ID.spec" <<EOF
Name: ${_ID}
Version: ${_VERSION/-*/}
Release: ${_VERSION/*-/}
Summary: ${_SUMMARY}
Group: Applications/Engineering
License: Multiple
Vendor: ${_VENDOR}
URL: ${_HOMEPAGE}
Packager: na <na>
Requires: libusb-1_0-0, libc.so.6, jre
AutoReqProv: no
%define _binary_payload w6.gzdio
%description
${_DESCRIPTION}
%files
${files}
%pre -p /bin/bash ${_PREINSTALL}
%post -p /bin/bash ${_POSTINSTALL}
%postun -p /bin/bash ${_POSTREMOVE}
EOF

	rpmbuild -bb\
	 --define "_topdir $PWD"\
	 --buildroot "$PWD/BUILDROOT"\
	 --target "$arch" "SPECS/$_ID.spec"\
	 --noclean --nocheck --quiet\
	 > /dev/null || exit 1

	_PACKAGE="$_TMPDIR/$_ID-$_VERSION.$arch.rpm"
	rm -f "$_PACKAGE"
	mv RPMS/*/*.rpm "$_PACKAGE" || exit 1
}


build-pet () {
	local arch=$1

	mkdir "$_ID-$_VERSION.$arch"
	pushd "$_ID-$_VERSION.$arch" >/dev/null

	write_files "$arch"

	local size=$(du -s -k | egrep -o '^[0-9]+')

	case "$arch" in
		amd64|x86_64) arch=x86_64 ;;
		i?86)         arch=i386   ;;
	esac

	echo 'Build pet package ...'

	local f01=$_ID-$_VERSION.$arch  #pkgname
	local f02=$_ID  #nameonly
	local f03=$_VERSION  #version
	local f04=  #pkgrelease
	local f05=  #category
	local f06=${size}K  #size
	local f07=  #path
	local f08=$_ID-$_VERSION.$arch.pet  #fullfilename
	local f09=+libusb-1.0,+libc6,+java-runtime  #dependencies
	local f10=$_SUMMARY  #description
	local f11=  #compileddistro
	local f12=  #compiledrelease
	local f13=  #repo

	write pet.specs <<< "$f01|$f02|$f03|$f04|$f05|$f06|$f07|$f08|$f09|$f10|$f11|$f12|$f13|"
	write pinstall.sh +x <<< "${_POSTINSTALL}"  # post-install
	write puninstall.sh +x <<< "${_POSTREMOVE}"  # post-uninstall

	popd >/dev/null

	_PACKAGE="$_TMPDIR/$_ID-$_VERSION.$arch.pet"
	rm -f "$_PACKAGE"
	tar -czvf "$_PACKAGE" * >/dev/null
	md5sum -b "$_PACKAGE" | cut -z -c 1-32 | tr -d '\0' >> "$_PACKAGE"
}


write_files () {
	local arch=$1

	echo 'Add program files ...'

	copy "$_SRCDIR"/{fwr,doc,version.txt} "opt/$_ID/"
	copy "$_SRCDIR"/lib/linux/$arch/* "opt/$_ID/lib/"
	copy "$_SRCDIR"/lib/*.jar "opt/$_ID/lib/"

	write "opt/$_ID/launch" +x <<EOF
#!/bin/bash
java -cp '/opt/$_ID/lib/*' com.owon.vds.tiny.Main
EOF


	echo 'Add desktop menu ...'

	mkdir -p usr/bin
	ln -s "/opt/$_ID/launch" "usr/bin/$_ID"

	for px in 32 48 64 96 128 256 ; do
		copy "$_SRCDIR/ico/icon-${px}.png" "usr/share/icons/hicolor/${px}x${px}/apps/$_ID.png"
	done

	write "usr/share/applications/$_ID.desktop" <<EOF
[Desktop Entry]
Name=${_NAME}
GenericName=${_GENERICNAME}
Comment=${_SUMMARY}
Icon=$_ID
Terminal=false
Type=Application
Exec=java -cp '/opt/$_ID/lib/*' com.owon.vds.tiny.Main
Categories=${_CATEGORIES};
StartupWMClass=com-owon-vds-tiny-Main
EOF

	write "usr/share/metainfo/$_ID.appdata.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop">
  <id>${_ID}.desktop</id>
  <name>${_NAME}</name>
  <summary>${_SUMMARY}</summary>
  <description><p>${_DESCRIPTION}</p></description>
  <launchable type="desktop-id">${_ID}.desktop</launchable>
  <url type="homepage">${_HOMEPAGE}</url>
  <provides><binary>${_ID}</binary></provides>
</component>
EOF

	echo 'Add usb permissions ...'

	write "etc/udev/rules.d/70-$_ID.rules" <<EOF
SUBSYSTEMS=="usb", ATTRS{idVendor}=="5345", ATTRS{idProduct}=="1234", MODE="0666"
EOF

}


copy () {
	# source, dest folder or file
	if [[ "${!#}" == */ ]] || [[ -d "${!#}" ]] ; then
		mkdir -p "${!#}"
		cp --no-preserve=mode,ownership -r "$@"
	else
		mkdir -p "$(dirname "${!#}")"
		cp --no-preserve=mode,ownership "$@"
	fi
}

write () {
	# 1: fname, 2: optional chmod, stdin: text
	mkdir -p "$(dirname "$1")"
	echo -e "$(</dev/stdin)" > "$1"
	[ -z "$2" ] || chmod "$2" "$1"
}

raise () {
	echo -e "Error: $1" >&2
	exit 1
}


main "$@"
