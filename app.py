# app.py
"""
Streamlit one-time voter app (Redis-backed) with optimistic UI
- When name is set it creates an entry immediately (choice='none')
- Voting updates counts optimistically and then performs Redis updates (rolled back on error)
- Reset Counts: zeros numeric counters, sets all names -> 'none', bumps reset_version (optimistic)
- Reset ALL: full wipe (counts + names) and unlock everyone (optimistic)
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

# ---------- Streamlit UI -------- --
st.set_page_config(page_title="Live Voter", layout="centered")
# auto-refresh every 3 seconds
st_autorefresh(interval=3000, key="refresh_counter")

st.title("Voter App 🧮 (Optimistic UI)")

# local/session flags (ensure defaults)
st.session_state.setdefault("voted", False)
st.session_state.setdefault("voted_choice", None)
st.session_state.setdefault("voter_name", "")
st.session_state.setdefault("last_reset_version", int(r.get(RESET_KEY) or 0))

# optimistic local counters (used for instant UI feedback)
# initialize once per session
if "local_yes" not in st.session_state:
    st.session_state.local_yes = int(r.get(YES_KEY) or 0)
if "local_no" not in st.session_state:
    st.session_state.local_no = int(r.get(NO_KEY) or 0)

# ---------- Name input ----------
# If a user sets their name, create an entry in Redis immediately with choice 'none'
if not st.session_state.voter_name:
    name_col1, name_col2 = st.columns([3, 1])
    with name_col1:
        # use a distinct key for the text_input so we can control when name is applied
        name_input = st.text_input("Enter your name to participate", key="voter_name_input")
    with name_col2:
        if st.button("Set Name"):
            if name_input and name_input.strip():
                cleaned = name_input.strip()
                # optimistic: set local session state immediately
                st.session_state.voter_name = cleaned
                st.session_state.voted = False
                st.session_state.voted_choice = None
                st.session_state.last_reset_version = int(r.get(RESET_KEY) or 0)
                # create user in Redis (attempt) but show UI immediately
                try:
                    r.hset(NAMES_HASH_KEY, cleaned, "none")
                except Exception as e:
                    # remote failed: rollback session_state and show error
                    st.session_state.voter_name = ""
                    st.session_state.voted = False
                    st.session_state.voted_choice = None
                    st.error(f"Failed to set name in backend: {e}")
                else:
                    st.rerun()
            else:
                st.warning("Please type a valid name before setting it.")
else:
    st.markdown(f"**Hello — {st.session_state.voter_name}**")

# check global reset version (auto-unlock if bumped)
current_reset_version = int(r.get(RESET_KEY) or 0)
if current_reset_version > st.session_state.get("last_reset_version", int(r.get(RESET_KEY) or 0)):
    st.session_state.voted = False
    st.session_state.voted_choice = None
    st.session_state.last_reset_version = current_reset_version

has_voted = bool(st.session_state.get("voted", False))

# helpers
def refresh_local_counters_from_redis():
    """Refresh the optimistic counters from Redis (used on full reloads)."""
    try:
        st.session_state.local_yes = int(r.get(YES_KEY) or 0)
        st.session_state.local_no = int(r.get(NO_KEY) or 0)
    except Exception:
        # keep local values if Redis can't be reached
        pass

def get_counts_and_table():
    """Return authoritative counts and a DataFrame of names -> choices.
    Note: this reads from Redis and is used for the authoritative table display.
    """
    try:
        yes = int(r.get(YES_KEY) or 0)
        no = int(r.get(NO_KEY) or 0)
        names_data = r.hgetall(NAMES_HASH_KEY) or {}
    except Exception:
        # fallback to local optimistic counters if Redis unreachable
        yes = st.session_state.local_yes
        no = st.session_state.local_no
        names_data = {}
    rows = []
    for name in sorted(names_data.keys()):
        choice = names_data.get(name)
        yes_val = 1 if choice == "yes" else 0
        no_val = 1 if choice == "no" else 0
        rows.append({"Name": name, "YES": yes_val, "NO": no_val})
    df = pd.DataFrame(rows)
    return yes, no, df

def cast_vote_remote(name: str, new_choice: str):
    """Perform the remote Redis update. Raise exceptions on failure."""
    if not name:
        raise ValueError("name required")
    prev = r.hget(NAMES_HASH_KEY, name) or "none"
    if prev == new_choice:
        # still set voted state in Redis if needed
        r.hset(NAMES_HASH_KEY, name, new_choice)
        return
    pipe = r.pipeline()
    if prev == "yes":
        pipe.decr(YES_KEY)
    elif prev == "no":
        pipe.decr(NO_KEY)
    if new_choice == "yes":
        pipe.incr(YES_KEY)
    elif new_choice == "no":
        pipe.incr(NO_KEY)
    pipe.hset(NAMES_HASH_KEY, name, new_choice)
    pipe.execute()

# voting helper that uses optimistic UI
def cast_vote_optimistic(name: str, new_choice: str):
    if not name:
        st.warning("Set your name before voting.")
        return

    # determine previous choice locally (prefer session_state, fallback to Redis)
    prev_local = st.session_state.get("voted_choice")
    if prev_local is None:
        try:
            prev_local = r.hget(NAMES_HASH_KEY, name) or "none"
        except Exception:
            prev_local = "none"

    # compute optimistic delta
    optimistic_yes = st.session_state.local_yes
    optimistic_no = st.session_state.local_no

    if prev_local == new_choice:
        # nothing to do (but mark as voted)
        st.session_state.voted = True
        st.session_state.voted_choice = new_choice
        return

    # apply optimistic changes locally
    if prev_local == "yes":
        optimistic_yes = max(0, optimistic_yes - 1)
    elif prev_local == "no":
        optimistic_no = max(0, optimistic_no - 1)

    if new_choice == "yes":
        optimistic_yes += 1
    elif new_choice == "no":
        optimistic_no += 1

    # commit optimistic UI
    st.session_state.local_yes = optimistic_yes
    st.session_state.local_no = optimistic_no
    st.session_state.voted = True
    st.session_state.voted_choice = new_choice

    # attempt remote update; on failure, rollback optimistic changes
    try:
        cast_vote_remote(name, new_choice)
        # sync last_reset_version after remote success
        st.session_state.last_reset_version = int(r.get(RESET_KEY) or 0)
    except Exception as e:
        # rollback
        # refresh authoritative counts from Redis where possible
        refresh_local_counters_from_redis()
        st.session_state.voted = False
        # attempt to retrieve the actual remote stored choice
        try:
            actual = r.hget(NAMES_HASH_KEY, name) or "none"
            st.session_state.voted_choice = actual if actual != "none" else None
        except Exception:
            st.session_state.voted_choice = None
        st.error(f"Failed to record vote remotely: {e}")

# optimistic reset counts (preserve names)
def reset_counts_optimistic():
    # optimistic UI: zero local counters, mark everyone as unlocked locally
    prev_yes = st.session_state.local_yes
    prev_no = st.session_state.local_no

    st.session_state.local_yes = 0
    st.session_state.local_no = 0
    st.session_state.voted = False
    st.session_state.voted_choice = None

    try:
        r.set(YES_KEY, 0)
        r.set(NO_KEY, 0)
        existing = r.hgetall(NAMES_HASH_KEY) or {}
        if existing:
            for n in existing.keys():
                r.hset(NAMES_HASH_KEY, n, "none")
        new_reset = r.incr(RESET_KEY)
        st.session_state.last_reset_version = int(new_reset)
    except Exception as e:
        # rollback on failure
        st.session_state.local_yes = prev_yes
        st.session_state.local_no = prev_no
        st.error(f"Failed to reset counts remotely: {e}")

# optimistic reset all (clear names too)
def reset_all_optimistic():
    prev_yes = st.session_state.local_yes
    prev_no = st.session_state.local_no
    prev_voter = st.session_state.voter_name
    prev_voted = st.session_state.voted
    prev_voted_choice = st.session_state.voted_choice
    prev_last_reset = st.session_state.last_reset_version

    # optimistic UI: clear everything
    st.session_state.local_yes = 0
    st.session_state.local_no = 0
    st.session_state.voted = False
    st.session_state.voted_choice = None
    st.session_state.last_reset_version = int(r.get(RESET_KEY) or 0)
    st.session_state.voter_name = ""

    if "voter_name_input" in st.session_state:
        del st.session_state["voter_name_input"]

    try:
        r.set(YES_KEY, 0)
        r.set(NO_KEY, 0)
        r.delete(NAMES_HASH_KEY)
        new_reset = r.incr(RESET_KEY)
        st.session_state.last_reset_version = int(new_reset)
    except Exception as e:
        # rollback local state on failure
        st.session_state.local_yes = prev_yes
        st.session_state.local_no = prev_no
        st.session_state.voted = prev_voted
        st.session_state.voted_choice = prev_voted_choice
        st.session_state.voter_name = prev_voter
        st.session_state.last_reset_version = prev_last_reset
        st.error(f"Failed to reset all remotely: {e}")

# sync local optimistic counters with authoritative Redis counts occasionally
# (this keeps UI consistent across long-lived sessions)
try:
    redis_yes = int(r.get(YES_KEY) or 0)
    redis_no = int(r.get(NO_KEY) or 0)
    # if remote differs substantially (e.g., after a reset by another browser), sync
    if abs(redis_yes - st.session_state.local_yes) > 1000 or abs(redis_no - st.session_state.local_no) > 1000:
        st.session_state.local_yes = redis_yes
        st.session_state.local_no = redis_no
except Exception:
    # ignore redis errors here; we'll display optimistic values
    pass

# Prepare UI
yes_count = st.session_state.local_yes
no_count = st.session_state.local_no
total_votes = yes_count + no_count

if st.session_state.voter_name:
    st.write(f"**Your Name:** {st.session_state.voter_name}  —  **Total Votes:** {total_votes}")

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    # optimistic voting button for YES
    if st.button("✅", disabled=has_voted or not st.session_state.voter_name):
        cast_vote_optimistic(st.session_state.voter_name, "yes")
        # ensure UI updates right away
        st.rerun()
    st.metric("Yes", yes_count)

with col2:
    # optimistic voting button for NO
    if st.button("❌", disabled=has_voted or not st.session_state.voter_name):
        cast_vote_optimistic(st.session_state.voter_name, "no")
        st.rerun()
    st.metric("No", no_count)

with col3:
    if st.button("🔄 Reset Counts"):
        reset_counts_optimistic()
        st.success("Counts have been reset and everyone is unlocked (optimistic).")
        st.rerun()

    if st.button("🔁 Reset ALL"):
        reset_all_optimistic()
        st.success("All cleared: counts reset, names cleared, everyone unlocked (optimistic).")
        st.rerun()

st.markdown("---")

# Display authoritative votes table where possible (falls back to empty if Redis unreachable)
auth_yes, auth_no, votes_df = get_counts_and_table()
if not votes_df.empty:
    totals = {"Name": "TOTAL", "YES": auth_yes, "NO": auth_no}
    votes_df = pd.concat([votes_df, pd.DataFrame([totals])], ignore_index=True)
    st.subheader("📊 Votes Table (authoritative)")
    st.table(votes_df)
else:
    # even if authoritative table empty, show optimistic totals
    if auth_yes == 0 and auth_no == 0 and (st.session_state.local_yes != 0 or st.session_state.local_no != 0):
        st.subheader("📊 Votes Table (optimistic totals shown above)")
    else:
        st.subheader("📊 No votes yet")

st.markdown("---")

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

# Debug info (optional)
st.caption(f"Internal reset_version: {int(r.get(RESET_KEY) or 0)}")