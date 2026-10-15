#!/bin/bash
# The G-2 gate worktree: a clean, detached checkout of the one committed candidate (Governance §37).
#
#   bash gate_worktree.sh create   # first allocation only: add the worktree, then verify it
#   bash gate_worktree.sh verify   # before and after every allocation
#   bash gate_worktree.sh remove   # after the last allocation, evidence preserved: verify, then remove
#
# Fail closed. Every command's exit status is checked explicitly and every identity is compared with
# its expected value; a command that fails is a failure, never an empty (clean-looking) answer. No
# pipeline carries a result, and no cleanup runs after a check in a way that could replace its status.
# The script prints `OK <action> ...` and exits 0 only when every check passed; otherwise it prints
# `FAIL: ...` to stderr and exits 1. It never retries, forces, resets or deletes anything but the
# temporary diff file it made and, for `remove`, the clean worktree itself.
#
# Repository access is through the owner's topic worktree (a worktree of the same vehicle module);
# the chassis's submodule checkout is not touched and no `submodule update` is run.

set -u

REPO=/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/b-39-ca87a9
COMMON=/home/john/space_chassis/.git/modules/docs/deep_research/vehicle
WT=/tmp/claude-1000/-home-john-space-chassis/a728e992-9471-46ab-9efe-ce550d7ece5f/scratchpad/gate-C-7a87eb8
SHA=7a87eb82cfef55dcc74248df41720883587ca7af
BASE=f75420cee5a1c7d4cd4ccb1ab8e95e5a9b96944f
TREE=ccc2782e350a6b9abe33d19db6884ac3fb82ec95
DIFF=0d4da11e9cbe56fcad7e09c48e027340d41f1bae438adfe8cce9dcc889a951d0

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

# The topic worktree must belong to the vehicle module and hold the candidate commit.
check_repo() {
    local common kind
    common=$(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir) || fail "rev-parse --git-common-dir in $REPO"
    [ "$common" = "$COMMON" ] || fail "common git dir $common != $COMMON"
    kind=$(git -C "$REPO" cat-file -t "$SHA") || fail "cat-file -t $SHA"
    [ "$kind" = commit ] || fail "$SHA is a $kind, not a commit"
}

# Clean detached checkout at SHA, parent BASE, tree TREE; nothing staged, modified or untracked
# (ignored files excepted); and the base-relative diff the v7 supervisor checks is DIFF.
verify() {
    local head parent tree rc rmrc status tmp sum
    [ -d "$WT" ] || fail "$WT is not a directory"
    head=$(git -C "$WT" rev-parse --verify HEAD) || fail "rev-parse HEAD"
    [ "$head" = "$SHA" ] || fail "HEAD $head != $SHA"
    parent=$(git -C "$WT" rev-parse --verify 'HEAD^1') || fail "rev-parse HEAD^1"
    [ "$parent" = "$BASE" ] || fail "parent $parent != $BASE"
    tree=$(git -C "$WT" rev-parse --verify 'HEAD^{tree}') || fail "rev-parse HEAD^{tree}"
    [ "$tree" = "$TREE" ] || fail "tree $tree != $TREE"

    git -C "$WT" symbolic-ref -q HEAD >/dev/null
    rc=$?
    [ "$rc" -eq 1 ] || fail "HEAD is not detached (symbolic-ref exit $rc)"

    git -C "$WT" diff --cached --quiet
    rc=$?
    [ "$rc" -eq 0 ] || fail "index differs from HEAD or git failed (exit $rc)"
    git -C "$WT" diff --quiet
    rc=$?
    [ "$rc" -eq 0 ] || fail "worktree differs from index or git failed (exit $rc)"
    status=$(git -C "$WT" status --porcelain=v1 --untracked-files=all) || fail "git status"
    [ -z "$status" ] || fail "not clean: $status"

    tmp=$(mktemp) || fail "mktemp"
    git -C "$WT" diff "$BASE" >"$tmp"
    rc=$?
    if [ "$rc" -ne 0 ]; then
        rm -f "$tmp" || fail "git diff $BASE exit $rc; removing $tmp also failed"
        fail "git diff $BASE exit $rc"
    fi
    sum=$(sha256sum "$tmp")
    rc=$?
    rm -f "$tmp"
    rmrc=$?
    [ "$rc" -eq 0 ] || fail "sha256sum exit $rc (removing $tmp exit $rmrc)"
    [ "$rmrc" -eq 0 ] || fail "removing $tmp exit $rmrc"
    sum=${sum%% *}
    [ "$sum" = "$DIFF" ] || fail "base-relative diff $sum != $DIFF"
}

# 0 if WT is registered as a worktree, 1 if not; any other outcome fails.
listed() {
    local list rc
    list=$(git -C "$REPO" worktree list --porcelain) || fail "git worktree list"
    printf '%s\n' "$list" | grep -Fxq "worktree $WT"
    rc=$?
    [ "$rc" -le 1 ] || fail "grep exit $rc"
    return "$rc"
}

[ "$#" -eq 1 ] || fail "usage: gate_worktree.sh create|verify|remove"
case "$1" in
create)
    check_repo
    [ ! -e "$WT" ] || fail "$WT already exists"
    if listed; then fail "$WT is already registered"; fi
    git -C "$REPO" worktree add --detach "$WT" "$SHA" || fail "git worktree add"
    verify
    ;;
verify)
    check_repo
    listed || fail "$WT is not a registered worktree"
    verify
    ;;
remove)
    check_repo
    listed || fail "$WT is not a registered worktree"
    verify
    timeout 60 git -C "$REPO" worktree remove "$WT" || fail "git worktree remove (not forced) failed or timed out"
    [ ! -e "$WT" ] || fail "$WT still exists"
    if listed; then fail "$WT is still registered"; fi
    ;;
*)
    fail "unknown action $1"
    ;;
esac
printf 'OK %s %s HEAD=%s tree=%s diff=%s\n' "$1" "$WT" "$SHA" "$TREE" "$DIFF"
