TEMPLATE = subdirs

CONFIG += debug_and_release
SUBDIRS = link
DIST = plugins.pri

win32 {
	SUBDIRS += bf2 cod2 cod4 cod5 l4d wolfet wow
}
