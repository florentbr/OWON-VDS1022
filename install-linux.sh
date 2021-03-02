#!/bin/bash

set -e
pushd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null

_SRCDIR=$(pwd)
_TMPDIR=$(readlink -f /tmp)

_ID='owon-vds-tiny'
_VERSION=$(<version.txt)
_FNAME="OWON-VDS1022"
_VENDOR='Copyright (C) Fujian Lilliput Optoelectronics Technology Co.,Ltd'
_NAME='OWON VDS1022 Oscilloscope'
_GENERICNAME='Oscilloscope'
_USAGE='Analyze an electrical signal'
_CATEGORIES='Electronics;Engineering'
_SUMMARY='Application for the OWON VDS1022 oscilloscope'
_CONTACT='florentbr@gmail.com'
_HOMEPAGE='https://github.com/florentbr/OWON-VDS1022'
_DESCRIPTION='Modified software for the OWON VDS1022 oscilloscope'
_PREINSTALL="
rm -fr /usr/share/$_ID /usr/lib/$_ID || true
"
_POSTINSTALL="
udevadm control --reload-rules
udevadm trigger
rm -f /home/*/.$_ID/preferences* || true
"
_POSTREMOVE="
rm -fr /home/*/.$_ID
"
_PACKAGE=


main () {

	[ "$EUID" = 0 ] || raise "This script requires eleveted privileges."

	echo "==========================================================="
	echo " Build package                                             "
	echo "==========================================================="

	echo 'Check environement ...'

	local arch=$(dpkg --print-architecture 2>/dev/null || uname -m)
	case "$arch" in
		x86_64)   arch=amd64 ;;
		i?86)     arch=i386  ;;
		aarch64)  arch=arm64 ;;
	esac
	[ -d "$_SRCDIR/lib/linux/$arch" ] || raise "Architecture not supported: ${arch}"

	local packager
	for packager in apt pacman dnf yum zypper ppm '' ; do
		[ -z "$packager" ] && raise 'Package manager not supported'
		[ -x "$(command -v $packager)" ] && break
	done

	local builddir="$_TMPDIR/oqosnrlfhwsbrfk"
	rm -rf "$builddir"
	install -d -m 755 "$builddir"
	pushd "$builddir" >/dev/null

	case $packager in
		apt)             build-deb $arch ;;
		pacman)          build-pac $arch ;;
		dnf|zipper|yum)  build-rpm $arch ;;
		ppm)             build-pet $arch ;;
		*)               raise "Packager not supported" ;;
	esac

	popd >/dev/null
	rm -rf "$builddir"

	printf "\nPackage:\n ${_PACKAGE}\n\n"


	echo "==========================================================="
	echo " Install package ${_PACKAGE##*/}                         "
	echo "==========================================================="

	env -i /bin/bash -c 'type java >/dev/null 2>&1' || raise "Java not found!"

	pushd "${_PACKAGE%/*}" >/dev/null

	case "$packager" in
		apt)     apt install --reinstall "$_PACKAGE" ;;
		pacman)  pacman -U "$_PACKAGE"               ;;
		dnf)     dnf install "$_PACKAGE"             ;;
		zipper)  zipper install "$_PACKAGE"          ;;
		yum)     yum install "$_PACKAGE"             ;;
		ppm)     pkg -f install "$_PACKAGE"          ;;
		*)       raise "Packager not supported"      ;;
	esac

	popd >/dev/null

	echo -e "\nDone!\n"

}


build-deb () {
	local arch=$1

	write_files "$arch" "lib/udev/rules.d"

	local size=$(du -s -k | egrep -o '^[0-9]+')

	echo 'Build debian package ...'

	write DEBIAN/control <<-EOF
	Package: ${_ID}
	Version: ${_VERSION}
	Depends: default-jre, libusb-1.0-0, libc6 (>= 2.15)
	Section: non-free/electronics
	Priority: optional
	Architecture: ${arch}
	Maintainer: <${_CONTACT}>
	Vendor: ${_VENDOR}
	Homepage: ${_HOMEPAGE}
	Installed-Size: ${size}
	Description: ${_SUMMARY}
	 ${_DESCRIPTION}
	EOF

	write DEBIAN/preinst  +x <<< "#!/bin/bash${_PREINSTALL}"
	write DEBIAN/postinst +x <<< "#!/bin/bash${_POSTINSTALL}"
	write DEBIAN/postrm   +x <<< "#!/bin/bash${_POSTREMOVE}"

	_PACKAGE="$_TMPDIR/$_FNAME-$_VERSION.$arch.deb"
	rm -f $_PACKAGE
	dpkg-deb -b -Zgzip . "$_PACKAGE" >/dev/null || exit 1
}


build-pac () {
	local arch=$1

	write_files "$arch" "usr/lib/udev/rules.d"

	local size=$(du -s -b | egrep -o '^[0-9]+')
	arch=${arch/amd64/x86_64}

	echo 'Build pacman package ...'

	write .PKGINFO +x <<-EOF
	pkgname = ${_ID}
	pkgbase = ${_ID}
	pkgver = ${_VERSION}
	pkgdesc = ${_SUMMARY}
	url = ${_HOMEPAGE}
	builddate = $(date -u '+%s')
	packager = ${_CONTACT}
	size = ${size}
	arch = ${arch}
	depend = java-runtime
	depend = libusb
	EOF

	write .INSTALL +x <<-EOF
	pre_install () {${_PREINSTALL}}
	post_install () {${_POSTINSTALL}}
	post_remove () {${_POSTREMOVE}}
	pre_upgrade () {${_PREINSTALL}}
	post_upgrade () {${_POSTINSTALL}}
	EOF

	_PACKAGE="$_TMPDIR/$_FNAME-$_VERSION.$arch.pac"
	rm -f "$_PACKAGE"
	tar -czvf "$_PACKAGE" .PKGINFO .INSTALL * >/dev/null || exit 1
}


build-rpm () {
	local arch=$1

	mkdir BUILD BUILDROOT RPMS SOURCES SPECS SRPMS
	pushd BUILDROOT >/dev/null

	write_files "$arch" "usr/lib/udev/rules.d"

	local files=$(find -type f | egrep -o '/.*')
	arch=${arch/amd64/x86_64}

	popd >/dev/null

	echo 'Build rpm package ...'

	write "SPECS/$_ID.spec" <<-EOF
	Name: ${_ID}
	Version: ${_VERSION/-*/}
	Release: ${_VERSION/*-/}
	Summary: ${_SUMMARY}
	Group: Applications/Engineering
	License: Multiple
	Vendor: ${_VENDOR}
	URL: ${_HOMEPAGE}
	Packager: ${_CONTACT}
	Requires: jre, libusb-1_0-0, libc.so.6
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

	_PACKAGE="$_TMPDIR/$_FNAME-$_VERSION.$arch.rpm"
	rm -f "$_PACKAGE"
	mv RPMS/*/*.rpm "$_PACKAGE" || exit 1
}


build-pet () {
	local arch=$1

	mkdir "$_FNAME-$_VERSION.$arch"
	pushd "$_FNAME-$_VERSION.$arch" >/dev/null

	write_files "$arch" "lib/udev/rules.d"

	local size=$(du -s -k | egrep -o '^[0-9]+')

	echo 'Build pet package ...'

	local f01=$_FNAME-$_VERSION.$arch  #pkgname
	local f02=$_FNAME  #nameonly
	local f03=$_VERSION  #version
	local f04=  #pkgrelease
	local f05=  #category
	local f06=${size}K  #size
	local f07=  #path
	local f08=$_FNAME-$_VERSION.$arch.pet  #fullfilename
	local f09=+default-jre,+libusb-1.0,+libc6  #dependencies
	local f10=$_SUMMARY  #description
	local f11=  #compileddistro
	local f12=  #compiledrelease
	local f13=  #repo

	write pet.specs <<< "$f01|$f02|$f03|$f04|$f05|$f06|$f07|$f08|$f09|$f10|$f11|$f12|$f13|"
	write pinstall.sh +x <<< "${_POSTINSTALL}"  # post-install
	write puninstall.sh +x <<< "${_POSTREMOVE}"  # post-uninstall

	popd >/dev/null

	_PACKAGE="$_TMPDIR/$_FNAME-$_VERSION.$arch.pet"
	rm -f "$_PACKAGE"
	tar -czvf "$_PACKAGE" * >/dev/null
	md5sum -b "$_PACKAGE" | cut -z -c 1-32 | tr -d '\0' >> "$_PACKAGE"
}


write_files () {
	local arch=$1
	local rulesdir=$2
	# local rulesdir=$(find {,usr/}lib/udev/rules.d 2>/dev/null | head -1)

	echo 'Add program files ...'

	copy "$_SRCDIR"/{fwr,jar,doc,version.txt} "usr/share/$_ID/"
	copy "$_SRCDIR/ico/icon48.png" "usr/share/pixmaps/$_ID.png"
	copy "$_SRCDIR/lib/linux/$arch"/* "usr/lib/$_ID/"

	write "usr/bin/$_ID" +x <<-EOF
	#!/bin/bash
	export LD_LIBRARY_PATH=/usr/lib/$_ID
	java -Djava.library.path='/usr/lib/$_ID' -Duser.dir="\$HOME/.$_ID" -cp '/usr/share/$_ID/jar/*' com.owon.vds.tiny.Main
	EOF

	write "usr/share/applications/$_ID.desktop" <<-EOF
	[Desktop Entry]
	Name=${_NAME}
	GenericName=${_GENERICNAME}
	Comment=${_USAGE}
	Exec=${_ID}
	Icon=${_ID}
	Terminal=false
	Type=Application
	Categories=${_CATEGORIES};
	StartupWMClass=com-owon-vds-tiny-Main
	EOF

	write "usr/share/appdata/$_ID.appdata.xml" <<-EOF
	<?xml version="1.0" encoding="UTF-8"?>
	​<component type="desktop">
	​  <id>${_ID}</id>
	​  <name>${_NAME}</name>
	​  <summary>${_SUMMARY}</summary>
	​  <description><p>${_DESCRIPTION}</p></description>
	​  <launchable type="desktop-id">${_ID}.desktop</launchable>
	​  <url type="homepage">${_HOMEPAGE}</url>
	​  <provides><binary>${_ID}</binary></provides>
	  <update_contact>${_CONTACT}</update_contact>
	​</component>
	EOF

	echo 'Add usb permissions ...'

	write "$rulesdir/70-$_ID.rules" <<-EOF
	SUBSYSTEMS=="usb", ATTRS{idVendor}=="5345", ATTRS{idProduct}=="1234", MODE="0666"
	EOF
}


copy () {
	if [[ "${!#}" == */ ]] || [[ -d "${!#}" ]] ; then
		mkdir -p "${!#}"
		cp --no-preserve=mode,ownership -r "$@"
	else
		mkdir -p "$(dirname "${!#}")"
		cp --no-preserve=mode,ownership "$@"
	fi
}

write () {
	mkdir -p "$(dirname "$1")"
	echo -e "$(cat -)" > "$1"
	[ -z "$2" ] || chmod "$2" "$1"
}

raise () {
	>&2 echo -e "Error: $1"
	exit 1
}


main "$@"
