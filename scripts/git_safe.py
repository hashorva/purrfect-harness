#!/usr/bin/env python3
"""The one safe git argv shared by harness scripts: no auto gc, no maintenance, no hooks."""

GIT = ("git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "core.hooksPath=/dev/null")


def argv(*args):
    """Return a git command with the shared safety prefix, then args."""
    return [*GIT, *args]
