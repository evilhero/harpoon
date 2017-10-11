#!/bin/bash
configfile="$conf_location"
configfile_secured='/tmp/harpoon.conf'

# check if the file contains something we don't want
if egrep -q -v '^#|^[^ ]*=[^;]*' "$configfile"; then
  echo "Config file is unclean, cleaning it..." >&2
  # filter the original to a new file
  egrep '^#|^[^ ]*=[^;&]*'  "$configfile" > "$configfile_secured"
  configfile="$configfile_secured"
fi

# now source it, either the original or the filtered variant
source "$configfile"

filename="$harpoon_location"
label="$harpoon_label"
multiple="$harpoon_multiplebox"

if [[ $APPLYLABEL == "true" ]]; then
    if [[ "$DEFAULTDIR" == */ ]]; then
        cd $DEFAULTDIR${label}
    else
        cd $DEFAULTDIR/${label}
    fi
else
    cd $DEFAULTDIR
fi

if [[ "${filename##*.}" == "mkv" || "${filename##*.}" == "avi" || "${filename##*.}" == "mp4" || "${filename##*.}" == "mpg" || "${filename##*.}" == "mov" || "${filename##*.}" == "cbr" || "${filename##*.}" == "cbz" ]]; then
    LCMD="pget -n 6 '$filename'"
else
    LCMD="mirror -P 2 --use-pget-n=6 '$filename'"
fi
if [[ $multiple -eq 0 || $multiple -eq 1 ]]; then
    HOST=$PP_HOST
    PORT=$PP_SSHPORT
    USER=$PP_USER
    PASS=$PP_PASSWD
else
    HOST=$PP_HOST2
    PORT=$PP_SSHPORT2
    USER=$PP_USER2
    PASS=$PP_PASSWD2
fi

lftp<<END_SCRIPT
open sftp://$HOST:$PORT
user $USER $PASS
$LCMD
bye
END_SCRIPT
