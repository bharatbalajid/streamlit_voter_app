# app.py
"""
One-Time Voter (Redis-backed counters)
- Global counts := Redis keys "votes:yes" and "votes:no"
- Per-browser lock := st.session_state.voted (local only)
- Reset clears Redis counters and unlocks the current browser session
Run: streamlit run app.py
"""

import streamlit as st
import redis

# ---------- Redis connection ----------
REDIS_URL = "redis://34.227.103.50:6379"   # <-- your Redis instance

r = redis.from_url(REDIS_URL, decode_responses=True)

YES_KEY = "votes:yes"
NO_KEY = "votes:no"

# ensure keys exist
if r.get(YES_KEY) is None:
    r.set(YES_KEY, 0)
if r.get(NO_KEY) is None:
    r.set(NO_KEY, 0)

# ---------- Streamlit UI ----------
st.set_page_config(page_title="One-Time Voter (Redis)", layout="centered")
st.title("✅ ❌ One-Time Voter App (Redis-backed)")

# local/session flags
st.session_state.setdefault("voted", False)
st.session_state.setdefault("voted_choice", None)

has_voted = bool(st.session_state.get("voted", False))

# read global counts from Redis
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

# fresh counts
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