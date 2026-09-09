"""Session-state "flash message" helper, shared across pages.

A message shown via st.success()/st.error() immediately before st.rerun()
never reaches the user - the rerun discards the current run's rendered
elements before they're displayed. Queue the message with flash() instead;
it's shown once, at the top of the next run, via render_pending_flash().
"""

import streamlit as st

_KEY = "_flash"


def flash(kind: str, message: str) -> None:
    """Queue `message` (kind: "success" | "error" | "warning" | "info") to
    show after the upcoming st.rerun()."""
    st.session_state[_KEY] = (kind, message)


def render_pending_flash() -> None:
    """Call once, near the top of a page, before any st.rerun() can fire."""
    pending = st.session_state.pop(_KEY, None)
    if pending:
        kind, message = pending
        getattr(st, kind)(message)
