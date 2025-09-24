# app.py
"""
One-Time Voter App (shared global counts)
- Global counts are stored in SQLite (votes.db) so all users see same totals
- Each browser session can vote only once (st.session_state.voted)
- Reset clears global counts and also unlocks the current session
Run: streamlit run app.py
"""

import sqlite3
import streamlit as st
from pathlib import Path
from datetime import datetime

DB_PATH = Path("votes.db")

# --- DB helpers ---
def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS counters (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                yes INTEGER NOT NULL DEFAULT 0,
                no INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            );
            """
        )
        # Ensure single row exists with id=1
        cur.execute("INSERT OR IGNORE INTO counters (id, yes, no, updated_at) VALUES (1, 0, 0, ?)",
                    (datetime.utcnow().isoformat(),))
        conn.commit()
    finally:
        conn.close()

def get_counts():
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT yes, no FROM counters WHERE id = 1")
        row = cur.fetchone()
        if row:
            return row[0], row[1]
        return 0, 0
    finally:
        conn.close()

def increment_yes():
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE counters SET yes = yes + 1, updated_at = ? WHERE id = 1", (datetime.utcnow().isoformat(),))
        conn.commit()
    finally:
        conn.close()

def increment_no():
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE counters SET no = no + 1, updated_at = ? WHERE id = 1", (datetime.utcnow().isoformat(),))
        conn.commit()
    finally:
        conn.close()

def reset_counts():
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE counters SET yes = 0, no = 0, updated_at = ? WHERE id = 1", (datetime.utcnow().isoformat(),))
        conn.commit()
    finally:
        conn.close()

# Initialize DB on app start
init_db()

# --- Streamlit UI ---
st.set_page_config(page_title="One-Time Voter (shared)", layout="centered")
st.title("✅ ❌ One-Time Voter App (shared counts)")

# Initialize local session flags (per browser)
st.session_state.setdefault("voted", False)
st.session_state.setdefault("voted_choice", None)

has_voted = bool(st.session_state.get("voted", False))

# Read global counts from DB (fresh each run)
yes_count, no_count = get_counts()

# Voting layout
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("✅", disabled=has_voted):
        # update global DB
        increment_yes()
        # set local lock
        st.session_state.voted = True
        st.session_state.voted_choice = "yes"
        st.experimental_rerun() if hasattr(st, "experimental_rerun") else st.rerun()
    st.metric("Yes", yes_count)

with col2:
    if st.button("❌", disabled=has_voted):
        increment_no()
        st.session_state.voted = True
        st.session_state.voted_choice = "no"
        st.experimental_rerun() if hasattr(st, "experimental_rerun") else st.rerun()
    st.metric("No", no_count)

with col3:
    if st.button("🔁 Reset counts & unlock my session"):
        reset_counts()
        # unlock this browser session so dev/testers can vote again
        st.session_state.voted = False
        st.session_state.voted_choice = None
        st.experimental_rerun() if hasattr(st, "experimental_rerun") else st.rerun()

st.markdown("---")

# Read fresh counts after any possible update (since we rerun after button clicks)
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

# Feedback about user's vote state
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

# Optional: debug view
# st.write("Session state:", dict(st.session_state))
# st.write("DB counts:", dict(yes=yes_count, no=no_count))