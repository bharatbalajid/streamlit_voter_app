# app.py
"""
One-Time Voter (Redis-backed, Live Counter, Global Reset)
- Global counts stored in Redis
- Per-browser lock for one-time voting
- Reset clears Redis counters AND globally unlocks all users via a reset_version key
- Live auto-refresh (every 2s) keeps everyone in sync

Enhancements in this file:
- Ask for voter's name initially and store it in session_state
- Show the voter's name and the counter (total votes)
- Store each voter's name in Redis set based on choice (yes_names / no_names)
- Display list of voter names under each count
- Two reset buttons:
    * "Reset Counts" — resets only the yes/no counters and clears names
    * "Reset All (counts + unlock everyone)" — resets counts, bumps reset_version, clears names, unlocks everyone
"""

import streamlit as st
import redis
from streamlit_autorefresh import st_autorefresh

# ---------- Redis connection ----------
REDIS_URL = "redis://34.227.103.50:6379"   # your Redis instance
r = redis.from_url(REDIS_URL, decode_responses=True)

YES_KEY = "votes:yes"
NO_KEY = "votes:no"
RESET_KEY = "votes:reset_version"
YES_NAMES_KEY = "votes:yes_names"
NO_NAMES_KEY = "votes:no_names"

# ensure keys exist
if r.get(YES_KEY) is None:
    r.set(YES_KEY, 0)
if r.get(NO_KEY) is None:
    r.set(NO_KEY, 0)
if r.get(RESET_KEY) is None:
    r.set(RESET_KEY, 0)

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Live Voter (Redis)", layout="centered")

# auto-refresh every 2 seconds
st_autorefresh(interval=2000, key="refresh_counter")

st.title("Voter App")

# local/session flags
st.session_state.setdefault("voted", False)
st.session_state.setdefault("voted_choice", None)
st.session_state.setdefault("last_reset_version", 0)
st.session_state.setdefault("voter_name", "")

# ---------- Name input ----------
if not st.session_state.voter_name:
    name_col1, name_col2 = st.columns([3, 1])
    with name_col1:
        name_input = st.text_input("Enter your name to participate", key="voter_name_input")
    with name_col2:
        if st.button("Set Name"):
            if name_input and name_input.strip():
                st.session_state.voter_name = name_input.strip()
                st.rerun()
            else:
                st.warning("Please type a valid name before setting it.")
else:
    st.markdown(f"**Hello — {st.session_state.voter_name}**")

# check global reset version
current_reset_version = int(r.get(RESET_KEY) or 0)
if current_reset_version > st.session_state.last_reset_version:
    st.session_state.voted = False
    st.session_state.voted_choice = None
    st.session_state.last_reset_version = current_reset_version

has_voted = bool(st.session_state.get("voted", False))

# helpers
def get_counts_and_names():
    yes = int(r.get(YES_KEY) or 0)
    no = int(r.get(NO_KEY) or 0)
    yes_names = r.smembers(YES_NAMES_KEY) or []
    no_names = r.smembers(NO_NAMES_KEY) or []
    return yes, no, yes_names, no_names

yes_count, no_count, yes_names, no_names = get_counts_and_names()

total_votes = yes_count + no_count

if st.session_state.voter_name:
    st.write(f"**Your Name:** {st.session_state.voter_name}  —  **Total Votes:** {total_votes}")

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("✅", disabled=has_voted or not st.session_state.voter_name):
        r.incr(YES_KEY)
        r.sadd(YES_NAMES_KEY, st.session_state.voter_name)
        st.session_state.voted = True
        st.session_state.voted_choice = "yes"
        st.session_state.last_reset_version = int(r.get(RESET_KEY) or 0)
        st.rerun()
    st.metric("Yes", yes_count)
    if yes_names:
        st.write(", ".join(yes_names))

with col2:
    if st.button("❌", disabled=has_voted or not st.session_state.voter_name):
        r.incr(NO_KEY)
        r.sadd(NO_NAMES_KEY, st.session_state.voter_name)
        st.session_state.voted = True
        st.session_state.voted_choice = "no"
        st.session_state.last_reset_version = int(r.get(RESET_KEY) or 0)
        st.rerun()
    st.metric("No", no_count)
    if no_names:
        st.write(", ".join(no_names))

with col3:
    if st.button("🔄 Reset Counts"):
        r.set(YES_KEY, 0)
        r.set(NO_KEY, 0)
        r.delete(YES_NAMES_KEY)
        r.delete(NO_NAMES_KEY)
        st.success("Counts and names have been reset (voter locks preserved).")
        st.rerun()

    if st.button("🔁 Reset ALL (counts + unlock everyone)"):
        r.set(YES_KEY, 0)
        r.set(NO_KEY, 0)
        r.delete(YES_NAMES_KEY)
        r.delete(NO_NAMES_KEY)
        r.incr(RESET_KEY)
        st.session_state.voted = False
        st.session_state.voted_choice = None
        st.session_state.last_reset_version = int(r.get(RESET_KEY))
        st.session_state.voter_name = ""
        if "voter_name_input" in st.session_state:
            del st.session_state["voter_name_input"]
        st.success("All cleared: counts reset, names cleared, everyone unlocked.")
        st.rerun()

st.markdown("---")

yes_count, no_count, yes_names, no_names = get_counts_and_names()
total_votes = yes_count + no_count

if total_votes > 0:
    yes_pct = (yes_count / total_votes) * 100
    no_pct = (no_count / total_votes) * 100
    st.subheader(f"📊 Total Votes: {total_votes}")
    st.progress(min(max(int(round(yes_pct)), 0), 100))
    st.write(f"✅ Yes: **{yes_count}** ({yes_pct:.1f}%)")
    if yes_names:
        st.caption("Yes voters: " + ", ".join(yes_names))
    st.write(f"❌ No: **{no_count}** ({no_pct:.1f}%)")
    if no_names:
        st.caption("No voters: " + ", ".join(no_names))
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
    if not st.session_state.voter_name:
        st.info("Please enter your name to vote. You can vote only once per browser session.")
    else:
        st.info("You can vote only once. After voting the buttons will be disabled for you.")

st.caption(f"Internal reset_version: {int(r.get(RESET_KEY) or 0)}")