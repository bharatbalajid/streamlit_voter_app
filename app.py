# app.py
"""
Streamlit one-time voter app (Redis-backed)
- When name is set it creates an entry immediately (choice='none')
- Voting updates counts and the stored per-name choice (handles switching vote)
- Reset Counts: zeros numeric counters, sets all names -> 'none' (names preserved)
- Reset ALL: full wipe (counts + names) and unlock everyone
Layout: keep current format but align buttons properly (vote buttons left/center, control panel right)
"""
import streamlit as st
import redis
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# ---------- Redis connection ----------
REDIS_URL = "redis://34.227.103.50:6379"   # update if needed
r = redis.from_url(REDIS_URL, decode_responses=True)

YES_KEY = "votes:yes"
NO_KEY = "votes:no"
RESET_KEY = "votes:reset_version"
NAMES_HASH_KEY = "votes:names"  # hash: {name: choice} where choice in {"yes","no","none"}

# ensure keys exist
if r.get(YES_KEY) is None:
    r.set(YES_KEY, 0)
if r.get(NO_KEY) is None:
    r.set(NO_KEY, 0)
if r.get(RESET_KEY) is None:
    r.set(RESET_KEY, 0)

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Live Voter", layout="centered")
# auto-refresh every 2 seconds
st_autorefresh(interval=2000, key="refresh_counter")

st.title("Voter App")

# local/session flags
st.session_state.setdefault("voted", False)
st.session_state.setdefault("voted_choice", None)
st.session_state.setdefault("last_reset_version", 0)
st.session_state.setdefault("voter_name", "")

# ---------- Helpers ----------
def get_counts_and_table():
    """Return yes_count, no_count, DataFrame of per-name votes."""
    yes = int(r.get(YES_KEY) or 0)
    no = int(r.get(NO_KEY) or 0)
    names_data = r.hgetall(NAMES_HASH_KEY) or {}
    rows = []
    for name in sorted(names_data.keys(), key=lambda x: x.lower()):
        choice = names_data.get(name)
        yes_val = 1 if choice == "yes" else 0
        no_val = 1 if choice == "no" else 0
        rows.append({"Name": name, "YES": yes_val, "NO": no_val})
    if rows:
        df = pd.DataFrame(rows)
    else:
        # empty df with columns to avoid downstream issues
        df = pd.DataFrame(columns=["Name", "YES", "NO"])
    return yes, no, df

def cast_vote(name: str, new_choice: str):
    """Handle vote switching: decrement previous and increment new; store per-name choice."""
    if not name:
        return
    prev = r.hget(NAMES_HASH_KEY, name) or "none"
    # if same choice, no counts change
    if prev == new_choice:
        return
    pipe = r.pipeline()
    # decrement previous counters if necessary
    if prev == "yes":
        pipe.decr(YES_KEY)
    elif prev == "no":
        pipe.decr(NO_KEY)
    # increment new
    if new_choice == "yes":
        pipe.incr(YES_KEY)
    elif new_choice == "no":
        pipe.incr(NO_KEY)
    # set new choice for name
    pipe.hset(NAMES_HASH_KEY, name, new_choice)
    pipe.execute()

def reset_counts():
    """Reset numeric counters to 0 and set each stored name to 'none' (preserve names).
       Also bump reset_version to unlock everyone."""
    r.set(YES_KEY, 0)
    r.set(NO_KEY, 0)
    existing = r.hgetall(NAMES_HASH_KEY) or {}
    if existing:
        for n in existing.keys():
            r.hset(NAMES_HASH_KEY, n, "none")
    new_reset = r.incr(RESET_KEY)
    # update session state to reflect unlock
    st.session_state.last_reset_version = int(new_reset)
    st.session_state.voted = False
    st.session_state.voted_choice = None

def reset_all():
    """Full wipe: clear counts and remove the names hash (no names preserved).
       Also bump reset_version to unlock everyone."""
    r.set(YES_KEY, 0)
    r.set(NO_KEY, 0)
    r.delete(NAMES_HASH_KEY)
    new_reset = r.incr(RESET_KEY)
    st.session_state.voted = False
    st.session_state.voted_choice = None
    st.session_state.last_reset_version = int(new_reset)
    # clear local name fields to force re-enter name
    st.session_state.voter_name = ""
    if "voter_name_input" in st.session_state:
        del st.session_state["voter_name_input"]

# ---------- Name input (inline, only if not set) ----------
if not st.session_state.voter_name:
    name_col, set_col = st.columns([3, 1])
    with name_col:
        name_input = st.text_input("Enter your name to participate", key="voter_name_input", placeholder="Type your full name")
    with set_col:
        if st.button("Set Name"):
            if name_input and name_input.strip():
                cleaned = name_input.strip()
                st.session_state.voter_name = cleaned
                # create user in Redis with no vote yet so they appear in the table
                r.hset(NAMES_HASH_KEY, cleaned, "none")
                # sync reset_version to avoid immediate unexpected unlock state
                st.session_state.voted = False
                st.session_state.voted_choice = None
                st.session_state.last_reset_version = int(r.get(RESET_KEY) or 0)
                st.experimental_rerun()
            else:
                st.warning("Please type a valid name before setting it.")
else:
    # When name already set → just greet, no input or button
    st.markdown(f"**Hello — {st.session_state.voter_name}**")

# check global reset version (auto-unlock if bumped externally)
current_reset_version = int(r.get(RESET_KEY) or 0)
if current_reset_version > st.session_state.last_reset_version:
    st.session_state.voted = False
    st.session_state.voted_choice = None
    st.session_state.last_reset_version = current_reset_version

has_voted = bool(st.session_state.get("voted", False))

# Fetch counts & table
yes_count, no_count, votes_df = get_counts_and_table()
total_votes = yes_count + no_count

if st.session_state.voter_name:
    st.write(f"**Your Name:** {st.session_state.voter_name}  —  **Total Votes:** {total_votes}")

# ---------- Voting + Controls Layout ----------
# Keep three-column layout like screenshot: left (✅), center (❌), right (controls)
vote_col1, vote_col2, control_col = st.columns([1, 1, 1])

with vote_col1:
    # large square-style button (keeps format)
    if st.button("✅", use_container_width=True, disabled=has_voted or not st.session_state.voter_name):
        cast_vote(st.session_state.voter_name, "yes")
        st.session_state.voted = True
        st.session_state.voted_choice = "yes"
        st.session_state.last_reset_version = int(r.get(RESET_KEY) or 0)
        st.experimental_rerun()
    st.metric("Yes", yes_count)

with vote_col2:
    if st.button("❌", use_container_width=True, disabled=has_voted or not st.session_state.voter_name):
        cast_vote(st.session_state.voter_name, "no")
        st.session_state.voted = True
        st.session_state.voted_choice = "no"
        st.session_state.last_reset_version = int(r.get(RESET_KEY) or 0)
        st.experimental_rerun()
    st.metric("No", no_count)

with control_col:
    # small spacer line so reset buttons align vertically similar to screenshot
    st.markdown("### ")
    # stacked reset buttons in right column (aligned)
    if st.button("🔄 Reset Counts", use_container_width=True):
        reset_counts()
        st.success("Counts have been reset and everyone is unlocked (names preserved).")
        st.experimental_rerun()

    st.markdown(" ")  # small gap between buttons to match screenshot spacing

    if st.button("🔁 Reset ALL", use_container_width=True):
        reset_all()
        st.success("All cleared: counts reset, names cleared, everyone unlocked.")
        st.experimental_rerun()

st.markdown("---")

# Display votes table
yes_count, no_count, votes_df = get_counts_and_table()
if not votes_df.empty:
    totals = {"Name": "TOTAL", "YES": yes_count, "NO": no_count}
    votes_df = pd.concat([votes_df, pd.DataFrame([totals])], ignore_index=True)
    st.subheader("📊 Votes Table")
    st.table(votes_df)
else:
    st.subheader("📊 No votes yet")

st.markdown("---")

# voting feedback to user
if has_voted:
    picked = st.session_state.get("voted_choice")
    if picked == "yes":
        st.success("You voted ✅ — thanks for participating!")
    elif picked == "no":
        st.success("You voted ❌ — thanks for participating!")
    else:
        st.success("You already voted — thanks for participating!")
else:
    if not st.session_state.voter_name:
        st.info("Please enter your name to vote. You can vote only once per browser session.")
    else:
        st.info("You can vote only once. After voting the buttons will be disabled for you.")

# Debug / small footer
st.caption(f"Internal reset_version: {int(r.get(RESET_KEY) or 0)}")