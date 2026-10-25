#!/bin/sh

# kill zcip $interface process (wjmoh@humaxdigital.com)

ps | grep "zcip $1" | grep -v "grep" | while read S1 S2
do
	echo "before kill zcip if"
	if [ -n $S1 ] ;
	then
		echo "kill zcip process " $S1
		kill $S1
	fi
done
