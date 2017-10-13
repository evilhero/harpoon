#!/bin/bash

filename="$harpoon_location"
label="$harpoon_label"
multiple="$harpoon_multiplebox"
applylabel="$harpoon_applylabel"
defaultdir="$harpoon_defaultdir"

if [[ "${applylabel}" == "true" ]]; then
    if [[ "${defaultdir}" == */ ]]; then
        cd ${defaultdir}${label}
    else
        cd ${defaultdir}/${label}
    fi
else
    cd ${defaultdir}
fi

if [[ "${filename##*.}" == "mkv" || "${filename##*.}" == "avi" || "${filename##*.}" == "mp4" || "${filename##*.}" == "mpg" || "${filename##*.}" == "mov" || "${filename##*.}" == "cbr" || "${filename##*.}" == "cbz" ]]; then
    LCMD="pget -n 6 '$filename'"
else
    LCMD="mirror -P 2 --use-pget-n=6 '$filename'"
fi
if [[ $multiple -eq 0 || $multiple -eq 1 ]]; then
    HOST="$harpoon_pp_host"
    PORT="$harpoon_pp_sshport"
    USER="$harpoon_pp_user"
    PASS="$harpoon_pp_passwd"
else
    HOST="$harpoon_pp_host2"
    PORT="$harpoon_pp_sshport2"
    USER="$harpoon_pp_user2"
    PASS="$harpoon_pp_passwd2"
fi

lftp<<END_SCRIPT
open sftp://${HOST}:${PORT}
user ${USER} ${PASS}
$LCMD
bye
END_SCRIPT
