#!/bin/sh

. /lib/lsb/init-functions
. /etc/default/rcS
if [ "$VERBOSE" != no ]; then
	log_begin_msg "Mounting local filesystems..."
fi

(
	mount -t jffs2 /dev/mtdblock1 /var/lib/humaxtv
	mount -t jffs2 /dev/mtdblock2 /var/lib/humaxtv_backup

) 2>&1 | grep -v '(already|nothing was) mounted'

