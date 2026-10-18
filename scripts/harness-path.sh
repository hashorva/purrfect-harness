#!/usr/bin/env bash
# Add the harness's common tool locations without disturbing caller PATH order.

_harness_candidates="${HARNESS_PATH_DIRS-/opt/homebrew/bin:/usr/local/bin}"
_harness_path="${PATH-}"
_harness_clean=""
_harness_seen=":"

while :; do
  _harness_entry="${_harness_path%%:*}"
  _harness_path="${_harness_path#*:}"
  _harness_is_candidate=0
  _harness_remaining="$_harness_candidates"
  while :; do
    _harness_candidate="${_harness_remaining%%:*}"
    _harness_remaining="${_harness_remaining#*:}"
    if [ "$_harness_entry" = "$_harness_candidate" ]; then
      _harness_is_candidate=1
      break
    fi
    [ "$_harness_remaining" != "$_harness_candidate" ] || break
  done
  if [ "$_harness_is_candidate" -eq 0 ] || [[ "$_harness_seen" != *":$_harness_entry:"* ]]; then
    if [ -n "$_harness_clean" ]; then
      _harness_clean="$_harness_clean:$_harness_entry"
    else
      _harness_clean="$_harness_entry"
    fi
    [ "$_harness_is_candidate" -eq 0 ] || _harness_seen="$_harness_seen$_harness_entry:"
  fi
  if [ "$_harness_path" = "$_harness_entry" ]; then
    break
  fi
done

_harness_prefix=""
_harness_remaining="$_harness_candidates"
while :; do
  _harness_candidate="${_harness_remaining%%:*}"
  _harness_remaining="${_harness_remaining#*:}"
  if [ -d "$_harness_candidate" ] && [[ "$_harness_seen" != *":$_harness_candidate:"* ]]; then
    if [ -n "$_harness_prefix" ]; then
      _harness_prefix="$_harness_prefix:$_harness_candidate"
    else
      _harness_prefix="$_harness_candidate"
    fi
    _harness_seen="$_harness_seen$_harness_candidate:"
  fi
  [ "$_harness_remaining" != "$_harness_candidate" ] || break
done

if [ -n "$_harness_prefix" ]; then
  PATH="$_harness_prefix${_harness_clean:+:$_harness_clean}"
else
  PATH="$_harness_clean"
fi
export PATH
unset _harness_candidates _harness_path _harness_clean _harness_seen _harness_entry \
  _harness_is_candidate _harness_remaining _harness_candidate _harness_prefix
