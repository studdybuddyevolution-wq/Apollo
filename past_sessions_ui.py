"""
past_sessions_ui.py — Apollo Omni AI: styled "past chats" browser

Drop-in replacement for conversation_memory.render_conversation_browser's
visuals. Uses the exact same ConversationMemory public API (list, search,
load) so no storage logic changes — only the rendering.
"""

import streamlit as st
import apollo_theme as theme
from conversation_memory import ConversationMemory


def render_past_sessions_panel(memory: ConversationMemory, user_email: str, key_prefix: str = "default"):
    """
    Args:
        memory: ConversationMemory instance
        user_email: User identifier
        key_prefix: Unique namespace for this panel's widget keys. Required
            because this panel can be rendered more than once per script run
            (e.g. once in the sidebar, once on the "Past Sessions" page) —
            without a distinct prefix, Streamlit raises
            StreamlitDuplicateElementKey on the second instance.
    """
    c = theme.COLORS
    st.markdown(
        f'<div style="font-size:13px;font-weight:600;color:{c["on-surface"]};'
        f'display:flex;align-items:center;gap:6px;margin-bottom:6px;">'
        f'{theme.icon("history", 16)} Past study sessions</div>',
        unsafe_allow_html=True,
    )

    search_term = st.text_input(
        "Search past conversations",
        key=f"{key_prefix}_conv_search",
        placeholder="Search by topic or tag...",
        label_visibility="collapsed",
    )

    convs = (
        memory.search_conversations(user_email, search_term)
        if search_term
        else memory.list_conversations(user_email)
    )

    if not convs:
        st.markdown(
            f'<div style="font-size:12px;color:{c["outline"]};padding:10px 0;">'
            f"No saved sessions yet — save a conversation above to see it here.</div>",
            unsafe_allow_html=True,
        )
        return

    for conv in convs:
        tags_html = "".join(
            f'<span style="font-size:10px;color:{c["primary-fixed-dim"]};'
            f'background:{c["primary-container"]}1a;padding:2px 8px;border-radius:999px;'
            f'margin-right:4px;">{t}</span>'
            for t in conv.get("tags", [])
        )
        st.markdown(
            f"""
            <div style="background:{c['surface-container-low']};border-radius:12px;
                        padding:12px 14px;margin-bottom:8px;">
                <div style="display:flex;justify-content:space-between;align-items:start;gap:8px;">
                    <div style="font-size:13px;font-weight:500;color:{c['on-surface']};">
                        {conv['topic'] or 'Untitled conversation'}
                    </div>
                    <div style="font-size:10px;color:{c['outline']};white-space:nowrap;">
                        {conv['created_at'][:10]}
                    </div>
                </div>
                <div style="font-size:11px;color:{c['on-surface-variant']};margin:4px 0 6px 0;">
                    {conv['message_count']} messages
                </div>
                <div>{tags_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander("Preview summary", expanded=False, key=f"{key_prefix}_preview_{conv['id']}"):
            summary = memory.get_conversation_summary(user_email, conv["id"])
            if summary:
                st.markdown(
                    f"<div style='font-size:12px;color:{c['on-surface-variant']};white-space:pre-wrap;'>{summary}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No preview summary available.")

        if st.button("Resume this session", key=f"{key_prefix}_resume_{conv['id']}", use_container_width=True):
            loaded = memory.load_conversation(user_email, conv["id"])
            st.session_state.loaded_conversation = loaded
            st.session_state.chat_history = loaded.get("history", [])
            st.success("Conversation loaded.")
            st.rerun()
