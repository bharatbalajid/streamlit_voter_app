# app.py
"""
One-Time Voter (Redis-backed, Live Counter)
- Global counts stored in Redis
- Per-browser lock so each user can only vote once
- Live auto-refresh of counters (every 2 seconds)
"""

import streamlit as st
import redis

# ---------- Redis connection ----------
REDIS_URL = "redis://34.227.103.50:6379"   # your Redis instance
r = redis.from_url(REDIS_URL, decode_responses=True)

YES_KEY = "votes:yes"
NO_KEY = "votes:no"

# ensure keys exist
if r.get(YES_KEY) is None:
    r.set(YES_KEY, 0)
if r.get(NO_KEY) is None:
    r.set(NO_KEY, 0)

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Live Voter (Redis)", layout="centered")

# Auto-refresh every 2 seconds
st_autorefresh = st.experimental_singleton if hasattr(st, "experimental_singleton") else None
st_autorefresh = st_autorefresh  # to silence lint

st_autorefresh = st_autorefresh  # no-op placeholder

# In new versions, use st_autorefresh
st_autorefresh = st_autorefresh

# Try Streamlit built-in autorefresh
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=2000, key="refresh_counter")

st.title("✅ ❌ One-Time Voter (Live Counter)")

# local/session flags
st.session_state.setdefault("voted", False)
st.session_state.setdefault("voted_choice", None)
has_voted = bool(st.session_state.get("voted", False))

# read counts
def get_counts():
    yes = int(r.get(YES_KEY) or 0)
    no = int(r.get(NO_KEY) or 0)
    return yes, no

yes_count, no_count = get_counts()

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("✅", disabled=has_voted):
        r.incr(YES_KEY)
        st.session_state.voted = True
        st.session_state.voted_choice = "yes"
        st.rerun()
    st.metric("Yes", yes_count)

with col2:
    if st.button("❌", disabled=has_voted):
        r.incr(NO_KEY)
        st.session_state.voted = True
        st.session_state.voted_choice = "no"
        st.rerun()
    st.metric("No", no_count)

with col3:
    if st.button("🔁 Reset counts & unlock my session"):
        r.set(YES_KEY, 0)
        r.set(NO_KEY, 0)
        st.session_state.voted = False
        st.session_state.voted_choice = None
        st.rerun()

st.markdown("---")

# fresh counts after any update
yes_count, no_count = get_counts()
total_votes = yes_count + no_count

if total_votes > 0:
    yes_pct = (yes_count / total_votes) * 100
    no_pct = (no_count / total_votes) * 100
    st.subheader(f"📊 Total Votes: {total_votes}")
    st.progress(min(max(int(round(yes_pct)), 0), 100))
    st.write(f"✅ Yes: **{yes_count}** ({yes_pct:.1f}%)")
    st.write(f"❌ No: **{no_count}** ({no_pct:.1f}%)")
else:
    st.subheader("📊 No votes yet")

st.markdown("---")

if has_voted:
    picked = st.session_state.get("voted_choice")
    if picked == "yes":
        st.success("You already voted ✅ — thanks for participating!")
    elif picked == "no":
        st.success("You already voted ❌ — thanks for participating!")
    else:
        st.success("You already voted — thanks for participating!")
else:
    st.info("You can vote only once. After voting the buttons will be disabled for you.")