#!/bin/sh
# Create, preallocate and loop-mount the ext4 image backing one bounded volume.
#
#   create_volume_image.sh NAME SIZE IMG MNT
#
# The image is fully allocated up front, never sparse, so a full volume cannot
# take host disk space beyond its fixed footprint; mkfs is given nodiscard so
# formatting keeps the blocks fallocate reserved. The filesystem root is
# root:root with mode 0755, so no service can rename, remove or replace the
# data/ directory compose binds. An existing image is never reformatted and
# never shrunk. A new image is built as IMG.tmp and given its final name only
# once it has the requested length and is fully allocated.
#
# data/ is never created here. When it is absent, the script prints the line
# that creates it, guarded so that it acts only on a mounted image whose root
# is root:root 0755. A mounted image whose root is not root:root, or is group-
# or other-writable, is not adopted.
#
# Nothing is followed through a symlink: a symlinked IMG, IMG.tmp, MNT or
# MNT/data is refused before anything is touched.
#
# Exit status: 0 when the volume is ready; 2 when steps for the operator were
# printed; 1 on invalid arguments or any other failure.
set -u
LC_ALL=C
export LC_ALL
PATH="$PATH:/usr/sbin:/sbin"

fail() {
    echo "create_volume_image.sh: $*" >&2
    exit 1
}

[ $# -eq 4 ] || fail "usage: create_volume_image.sh NAME SIZE IMG MNT"
NAME=$1
SIZE=$2
IMG=$3
MNT=$4
TMP="$IMG.tmp"
DATA="$MNT/data"

case $NAME in
    [a-z]*) ;;
    *) fail "invalid name: '$NAME'" ;;
esac
case $NAME in
    *[!a-z0-9_]*) fail "invalid name: '$NAME'" ;;
esac
case $SIZE in
    *[KMGT]) ;;
    *) fail "invalid size: '$SIZE'" ;;
esac
case ${SIZE%?} in
    '' | *[!0-9]*) fail "invalid size: '$SIZE'" ;;
esac
case $IMG in
    /*) ;;
    *) fail "IMG must be an absolute path: '$IMG'" ;;
esac
case $MNT in
    /*) ;;
    *) fail "MNT must be an absolute path: '$MNT'" ;;
esac

for path in "$IMG" "$TMP" "$MNT" "$DATA"; do
    if [ -L "$path" ]; then
        fail "refusing a symlink: $path"
    fi
done

WANT=$(numfmt --from=iec "$SIZE") || fail "cannot convert size: $SIZE"

STATUS=0

# Print steps for the operator, one argument per line.
remedy() {
    printf '%s\n' "$@"
    STATUS=2
}

# A path single-quoted for the commands printed for the operator to run.
quoted() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

Q_IMG=$(quoted "$IMG")
Q_TMP=$(quoted "$TMP")
Q_MNT=$(quoted "$MNT")
Q_DATA=$(quoted "$DATA")

# The bytes allocated to a file, without following a link.
allocated_bytes() {
    blocks=$(stat -c %b -- "$1") || return 1
    unit=$(stat -c %B -- "$1") || return 1
    echo $((blocks * unit))
}

GROW=no
if [ -e "$IMG" ]; then
    [ -f "$IMG" ] || fail "$IMG exists and is not a regular file"
    TYPE=$(blkid -p -s TYPE -o value "$IMG" 2>/dev/null) || TYPE=
    if [ "$TYPE" != ext4 ]; then
        echo "$IMG exists and is not an ext4 filesystem (${TYPE:-none found}); it was not reformatted."
        echo "remove it by hand once it holds nothing you need, then rerun."
        exit 2
    fi
    LENGTH=$(stat -c %s -- "$IMG") || fail "cannot read the length of $IMG"
    ALLOCATED=$(allocated_bytes "$IMG") || fail "cannot read the allocation of $IMG"
    if [ "$ALLOCATED" -lt "$LENGTH" ]; then
        remedy "$IMG is sparse: $ALLOCATED of its $LENGTH bytes are allocated. with the stack down, run:" \
            "  fallocate -l $LENGTH $Q_IMG"
    fi
    if [ "$LENGTH" -lt "$WANT" ]; then
        GROW=yes
    elif [ "$LENGTH" -gt "$WANT" ]; then
        echo "warning: $IMG is $LENGTH bytes, more than its configured $SIZE ($WANT bytes); images are never shrunk" >&2
    fi
else
    if [ -e "$TMP" ]; then
        [ -f "$TMP" ] || fail "$TMP exists and is not a regular file"
        # The creator's own unfinished file, never mounted and never given the
        # final name. It is removed only when losetup answers and lists no
        # device using it.
        if ATTACHED=$(losetup -j "$TMP" 2>/dev/null) && [ -z "$ATTACHED" ]; then
            rm -f -- "$TMP" || fail "cannot remove $TMP"
        else
            echo "$TMP is an unfinished image from an earlier run; losetup lists a device using it, or could not be asked, so it was left in place."
            if [ -n "$ATTACHED" ]; then
                echo "detach the devices using it, remove it, then rerun:"
                printf '%s\n' "$ATTACHED" | cut -d: -f1 | sed 's/^/  sudo losetup -d /'
            else
                echo "detach any device the first command lists with sudo losetup -d DEVICE, remove it, then rerun:"
                echo "  sudo losetup -j $Q_TMP"
            fi
            echo "  rm -f $Q_TMP"
            exit 2
        fi
    fi
    mkdir -p -- "$(dirname -- "$IMG")" || fail "cannot create the directory of $IMG"
    fallocate -l "$SIZE" "$TMP" || fail "fallocate failed for $TMP"
    mkfs.ext4 -q -F -m 0 \
        -E root_owner=0:0,nodiscard,lazy_itable_init=0,lazy_journal_init=0 "$TMP" \
        || fail "mkfs.ext4 failed for $TMP"
    LENGTH=$(stat -c %s -- "$TMP") || fail "cannot read the length of $TMP"
    ALLOCATED=$(allocated_bytes "$TMP") || fail "cannot read the allocation of $TMP"
    [ "$LENGTH" -eq "$WANT" ] \
        || fail "$TMP is $LENGTH bytes, not the requested $WANT; it was not given the final name"
    [ "$ALLOCATED" -ge "$LENGTH" ] \
        || fail "$TMP has $ALLOCATED of its $LENGTH bytes allocated; it was not given the final name"
    mv -T -- "$TMP" "$IMG" || fail "cannot rename $TMP to $IMG"
    echo "created $IMG ($SIZE, preallocated)" >&2
fi

# The mount point's mode is set only while nothing is mounted on it.
MOUNTED=no
if [ ! -e "$MNT" ]; then
    mkdir -p -- "$(dirname -- "$MNT")" || fail "cannot create the directory of $MNT"
    mkdir -m 0555 -- "$MNT" || fail "cannot create $MNT"
elif [ ! -d "$MNT" ]; then
    fail "$MNT exists and is not a directory"
elif mountpoint -q "$MNT"; then
    MOUNTED=yes
    echo "mounted: $MNT" >&2
else
    ENTRY=$(find "$MNT" -mindepth 1 -maxdepth 1 -print -quit) || fail "cannot list $MNT"
    if [ -n "$ENTRY" ]; then
        echo "$MNT is not mounted and not empty; it was not mounted over, because that would hide its contents."
        echo "move its contents elsewhere by hand, then rerun."
        exit 2
    fi
    MODE=$(stat -c %a -- "$MNT") || fail "cannot read the mode of $MNT"
    if [ "$MODE" != 555 ]; then
        OWNER=$(stat -c %u -- "$MNT") || fail "cannot read the owner of $MNT"
        if [ "$OWNER" = "$(id -u)" ]; then
            chmod 0555 -- "$MNT" || fail "cannot set the mode of $MNT"
        else
            remedy "$MNT is owned by uid $OWNER; with nothing mounted on it, run:" \
                "  mountpoint -q $Q_MNT || sudo chmod 0555 $Q_MNT"
        fi
    fi
fi

if [ "$MOUNTED" = no ]; then
    if sudo -n mount -o loop,nosuid,nodev "$IMG" "$MNT" 2>/dev/null; then
        MOUNTED=yes
        echo "mounted $IMG at $MNT" >&2
    else
        remedy "$IMG is not mounted. run:" \
            "  sudo mount -o loop,nosuid,nodev $Q_IMG $Q_MNT"
    fi
fi

# A mounted image's root must be root:root and writable by neither group nor
# other, or a service could have placed an entry at data. An image formatted
# under an older layout can have a root a service owned; it is not adopted.
# An image that is not yet mounted is held to the same rule by the stat guard
# in the printed data/ line, which runs after the mount.
if [ "$MOUNTED" = yes ]; then
    ROOT_STAT=$(stat -c '%u %g %a' -- "$MNT") || fail "cannot inspect $MNT"
    # shellcheck disable=SC2086
    set -- $ROOT_STAT
    [ $# -eq 3 ] || fail "cannot inspect $MNT"
    case $3 in
        '' | *[!0-7]*) fail "cannot read the mode of $MNT" ;;
    esac
    if [ "$1" != 0 ] || [ "$2" != 0 ] || [ $((0$3 & 022)) -ne 0 ]; then
        echo "image root is $1:$2 $3; remove the image by hand, unmounting it first: $IMG"
        exit 2
    fi
fi

if [ -L "$DATA" ]; then
    fail "refusing a symlink: $DATA"
fi
# mkdir refuses any existing entry, a symlink included, and chown -h never
# follows a link; the stat guard refuses an image root other than root:root 0755.
if [ ! -e "$DATA" ]; then
    remedy "$DATA does not exist. once the image is mounted, run:" \
        "  mountpoint -q $Q_MNT && [ \"\$(stat -c %u:%g:%a $Q_MNT)\" = 0:0:755 ] && sudo mkdir -m 0755 $Q_DATA && sudo chown -h 1000:1000 $Q_DATA"
fi

if [ "$GROW" = yes ]; then
    remedy "$IMG is $LENGTH bytes; $NAME is configured at $SIZE ($WANT bytes). once it is mounted, grow it:" \
        "  fallocate -l $SIZE $Q_IMG" \
        "  sudo losetup -c \"\$(losetup -j $Q_IMG | cut -d: -f1)\"" \
        "  sudo resize2fs \"\$(losetup -j $Q_IMG | cut -d: -f1)\""
fi

if [ "$STATUS" -eq 0 ]; then
    echo "ready: $NAME at $MNT" >&2
fi
exit "$STATUS"
