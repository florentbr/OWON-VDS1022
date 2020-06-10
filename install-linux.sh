#!/bin/bash

set -e
pushd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null

THIS_DIR=$(pwd)
TEMP_DIR=$(readlink -f /tmp)

PK_ID='owon-vds-tiny'
PK_VERSION=$(<"$THIS_DIR/version.txt")
PK_FNAME="OWON-VDS1022"
PK_VENDOR='Copyright (C) Fujian Lilliput Optoelectronics Technology Co.,Ltd'
PK_NAME='OWON VDS1022 Oscilloscope'
PK_GENERICNAME='Oscilloscope'
PK_USAGE='Analyze an electrical signal'
PK_CATEGORIES='Electronics;Engineering'
PK_SUMMARY='Application for the OWON VDS1022 oscilloscope'
PK_CONTACT='florentbr@gmail.com'
PK_HOMEPAGE='https://github.com/florentbr/Owon-VDS1022'
PK_APP_DIR="/usr/share/$PK_ID"
PK_LIB_DIR="/usr/lib/$PK_ID"
PK_DESCRIPTION='Unofficial release with a few fixes and improvements:
 * New shortcuts: single trigger, trigger level, offsets, coupling, inversion, reset ...
 * Disabled annoying dock animations
 * Disabled leave/stop confirmation while recording/playing
 * ...'
PK_PREINSTALL="
rm -f /etc/udev/rules.d/*owon*.rules
"
PK_POSTINSTALL="
udevadm control --reload-rules
udevadm trigger
rm -f /home/*/.$PK_ID/preferences* || true
"
PK_POSTREMOVE="
rm -rf /home/*/.$PK_ID
"


main () {

	[ "$EUID" = 0 ] || raise "This script requires eleveted privileges."

	echo "==========================================================="
	echo " Build package                                             "
	echo "==========================================================="

	local arch=$(dpkg --print-architecture 2>/dev/null || uname -m)
	case "$arch" in
		x86_64)   arch=amd64 ;;
		i?86)     arch=i386  ;;
		aarch64)  arch=arm64 ;;
	esac
	[ -d "$THIS_DIR/lib/linux/$arch" ] || raise "Architecture not supported: ${arch}"

	local packager
	for packager in apt pacman dnf yum zypper ppm '' ; do
		[ -z "$packager" ] && raise 'Package manager not supported'
		[ -x "$(command -v $packager)" ] && break
	done

	local builddir="$TEMP_DIR/oqosnrlfhwsbrfk"
	rm -rf "$builddir"
	install -d -m 755 "$builddir"
	pushd "$builddir" >/dev/null

	case "$packager" in
		apt)             build-deb $arch ;;
		pacman)          build-pac $arch ;;
		dnf|zipper|yum)  build-rpm $arch ;;
		ppm)             build-pet $arch ;;
		*)               raise "Packager not supported" ;;
	esac

	popd >/dev/null
	rm -rf "$builddir"

	printf "\nPackage:\n ${PK_PACKAGE}\n\n"


	echo "==========================================================="
	echo " Install package ${PK_PACKAGE##*/}                         "
	echo "==========================================================="

	pushd "${PK_PACKAGE%/*}" >/dev/null

	case "$packager" in
		apt)     apt install --reinstall "$PK_PACKAGE" ;;
		pacman)  pacman -U "$PK_PACKAGE"         ;;
		dnf)     dnf install "$PK_PACKAGE"       ;;
		zipper)  zipper install "$PK_PACKAGE"    ;;
		yum)     yum install "$PK_PACKAGE"       ;;
		ppm)     pkg -f install "$PK_PACKAGE"    ;;
		*)       raise "Packager not supported"  ;;
	esac

	popd >/dev/null

	env -i /bin/bash -c 'type java >/dev/null 2>&1' || raise "Java not found!"

	echo -e "\nDone!\n"

}


build-deb () {
	local arch=$1

	PK_ARCH=$arch
	PK_PACKAGE="$TEMP_DIR/$PK_FNAME-$PK_VERSION.$PK_ARCH.deb"
	PK_RULES_DIR='/lib/udev/rules.d'

	add_files "$arch"

	echo 'Build debian package ...'

	write ./DEBIAN/control <<-EOF
	Package: ${PK_ID}
	Version: ${PK_VERSION}
	Depends: default-jre, libc6 (>= 2.15)
	Section: non-free/electronics
	Priority: optional
	Architecture: ${PK_ARCH}
	Maintainer: <${PK_CONTACT}>
	Vendor: ${PK_VENDOR}
	Homepage: ${PK_HOMEPAGE}
	Installed-Size: $(expr $PK_SIZE / 1024)
	Description: ${PK_SUMMARY}
	 ${PK_DESCRIPTION}
	EOF

	write ./DEBIAN/preinst  +x <<< "#!/bin/bash${PK_PREINSTALL}"
	write ./DEBIAN/postinst +x <<< "#!/bin/bash${PK_POSTINSTALL}"
	write ./DEBIAN/postrm   +x <<< "#!/bin/bash${PK_POSTREMOVE}"

	rm -f $PK_PACKAGE
	dpkg-deb -b -Zgzip . "$PK_PACKAGE" >/dev/null || exit 1
}


build-pac () {
	local arch=$1

	PK_ARCH=${arch/amd64/x86_64}
	PK_PACKAGE="$TEMP_DIR/$PK_FNAME-$PK_VERSION.$PK_ARCH.pac"
	PK_RULES_DIR='/usr/lib/udev/rules.d'

	add_files "$arch"

	echo 'Build pacman package ...'

	write .PKGINFO +x <<-EOF
	pkgname = ${PK_ID}
	pkgbase = ${PK_ID}
	pkgver = ${PK_VERSION}
	pkgdesc = ${PK_SUMMARY}
	url = ${PK_HOMEPAGE}
	builddate = $(date -u '+%s')
	packager = ${PK_CONTACT}
	size = ${PK_SIZE}
	arch = ${PK_ARCH}
	depend = java-runtime
	EOF

	write .INSTALL +x <<-EOF
	pre_install () {${PK_PREINSTALL}}
	post_install () {${PK_POSTINSTALL}}
	post_remove () {${PK_POSTREMOVE}}
	pre_upgrade () {${PK_PREINSTALL}}
	post_upgrade () {${PK_POSTINSTALL}}
	EOF

	rm -f "$PK_PACKAGE"
	tar -czvf "$PK_PACKAGE" .PKGINFO .INSTALL * >/dev/null || exit 1
}


build-rpm () {
	local arch=$1

	PK_ARCH=${arch/amd64/x86_64}
	PK_PACKAGE="$TEMP_DIR/$PK_FNAME-$PK_VERSION.$PK_ARCH.rpm"
	PK_RULES_DIR='/usr/lib/udev/rules.d'

	mkdir BUILD BUILDROOT RPMS SOURCES SPECS SRPMS
	pushd ./BUILDROOT >/dev/null

	add_files "$arch"

	popd >/dev/null

	echo 'Build rpm package ...'

	write "./SPECS/$PK_ID.spec" <<-EOF
	Name: ${PK_ID}
	Version: ${PK_VERSION/-*/}
	Release: ${PK_VERSION/*-/}
	Summary: ${PK_SUMMARY}
	Group: Applications/Engineering
	License: Multiple
	Vendor: ${PK_VENDOR}
	URL: ${PK_HOMEPAGE}
	Packager: ${PK_CONTACT}
	Requires: jre, libc.so.6
	AutoReqProv: no
	%define _binary_payload w6.gzdio
	%description
	${PK_DESCRIPTION}
	%files
	${PK_FILES}
	%pre -p /bin/bash ${PK_PREINSTALL}
	%post -p /bin/bash ${PK_POSTINSTALL}
	%postun -p /bin/bash ${PK_POSTREMOVE}
	EOF

	rpmbuild -bb \
	  --define "_topdir $PWD" \
	  --buildroot "$PWD/BUILDROOT" \
	  --target "$PK_ARCH" "./SPECS/$PK_ID.spec" \
	  --noclean --nocheck --quiet \
	  > /dev/null || exit 1

	rm -f "$PK_PACKAGE"
	mv ./RPMS/*/*.rpm "$PK_PACKAGE" || exit 1
}


build-pet () {
	local arch=$1

	PK_ARCH=$arch
	PK_PACKAGE="$TEMP_DIR/$PK_FNAME-$PK_VERSION.$PK_ARCH.pet"
	PK_RULES_DIR='/lib/udev/rules.d'

	mkdir "$PK_FNAME-$PK_VERSION.$PK_ARCH"
	pushd "$PK_FNAME-$PK_VERSION.$PK_ARCH" >/dev/null

	add_files "$arch"

	echo 'Build pet package ...'

	local f01=$PK_FNAME-$PK_VERSION.$PK_ARCH  #pkgname
	local f02=$PK_FNAME  #nameonly
	local f03=${PK_VERSION}  #version
	local f04=  #pkgrelease
	local f05=  #category
	local f06=$(expr $PK_SIZE / 1024)K  #size
	local f07=  #path
	local f08=$PK_FNAME-$PK_VERSION.$PK_ARCH.pet  #fullfilename
	local f09=+default-jre,+libc6  #dependencies
	local f10=$PK_SUMMARY  #description
	local f11=  #compileddistro
	local f12=  #compiledrelease
	local f13=  #repo

	write pet.specs <<< "$f01|$f02|$f03|$f04|$f05|$f06|$f07|$f08|$f09|$f10|$f11|$f12|$f13|"
	write pinstall.sh +x <<< "${PK_PREINSTALL}${PK_POSTINSTALL}"
	write puninstall.sh +x <<< "${PK_POSTREMOVE}"

	popd >/dev/null

	rm -f "$PK_PACKAGE"
	tar -czvf "$PK_PACKAGE" * >/dev/null
	md5sum -b "$PK_PACKAGE" | cut -z -c 1-32 | tr -d '\0' >> "$PK_PACKAGE"
}


add_files () {
	local arch=$1

	echo 'Add usb permissions ...'

	write ".$PK_RULES_DIR/70-$PK_ID.rules" <<-EOF
	SUBSYSTEMS=="usb", ATTRS{idVendor}=="5345", ATTRS{idProduct}=="1234", MODE="0666"
	EOF

	echo 'Add application files ...'

	copy ".$PK_LIB_DIR/" "$THIS_DIR/lib/linux/$arch"/*
	copy ".$PK_APP_DIR/" "$THIS_DIR/fwr" "$THIS_DIR/jar" "$THIS_DIR/doc" "$THIS_DIR/version.txt"

	write "./usr/bin/$PK_ID" +x <<-EOF
	#!/bin/bash
	export LD_LIBRARY_PATH=$PK_LIB_DIR
	java -Djava.library.path='$PK_LIB_DIR' -Duser.dir="\$HOME/.$PK_ID" -cp '$PK_APP_DIR/jar/*' com.owon.vds.tiny.Main
	EOF

	echo 'Add launcher ...'

	copy "./usr/share/pixmaps/$PK_ID.png" "$THIS_DIR/ico/icon48.png"

	write "./usr/share/applications/$PK_ID.desktop" <<-EOF
	[Desktop Entry]
	Name=${PK_NAME}
	GenericName=${PK_GENERICNAME}
	Comment=${PK_USAGE}
	Exec=${PK_ID}
	Icon=${PK_ID}
	Terminal=false
	Type=Application
	Categories=${PK_CATEGORIES};
	StartupWMClass=com-owon-vds-tiny-Main
	EOF

	write "./usr/share/appdata/$PK_ID.appdata.xml" <<-EOF
	<?xml version="1.0" encoding="UTF-8"?>
	​<component type="desktop">
	​  <id>${PK_ID}</id>
	​  <name>${PK_NAME}</name>
	​  <summary>${PK_SUMMARY}</summary>
	​  <description><p>${PK_DESCRIPTION}</p></description>
	​  <launchable type="desktop-id">${PK_ID}.desktop</launchable>
	​  <url type="homepage">${PK_HOMEPAGE}</url>
	​  <provides><binary>${PK_ID}</binary></provides>
	  <update_contact>${PK_CONTACT}</update_contact>
	​</component>
	EOF

	PK_FILES=$(find -type f | egrep -o '/.*')
	PK_SIZE=$(du -s -b | egrep -o '^[0-9]+')
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
	>&2 echo -e "Error: $1"
	exit 1
}


main "$@"
