# app.py
"""
One-Time Voter App (single-file)
- Buttons: ✅ and ❌
- User can vote only once per browser session (stored in st.session_state)
- Reset (🔁) clears global counters AND unlocks the current browser/session
- Shows total votes, percentages, and a progress bar
Run: streamlit run app.py
"""

import streamlit as st

st.set_page_config(page_title="One-Time Voter", layout="centered")

st.title("✅ ❌ One-Time Voter App")

# --- Initialize session state keys safely ---
st.session_state.setdefault("yes", 0)
st.session_state.setdefault("no", 0)
st.session_state.setdefault("voted", False)         # boolean: has this browser/session voted?
st.session_state.setdefault("voted_choice", None)   # "yes" or "no" (optional informative)

# Guarantee we use a boolean for disabling widgets
has_voted = bool(st.session_state.get("voted", False))

# --- Voting layout ---
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("✅", disabled=has_voted):
        st.session_state.yes += 1
        st.session_state.voted = True
        st.session_state.voted_choice = "yes"
        st.rerun()
    st.metric("Yes", st.session_state.yes)

with col2:
    if st.button("❌", disabled=has_voted):
        st.session_state.no += 1
        st.session_state.voted = True
        st.session_state.voted_choice = "no"
        st.rerun()
    st.metric("No", st.session_state.no)

with col3:
    # This Reset clears counters AND unlocks the current browser/session
    if st.button("🔁 Reset counts"):
        # clear global counters
        st.session_state.yes = 0
        st.session_state.no = 0
        # unlock this browser/session so the user can vote again
        st.session_state.voted = False
        st.session_state.voted_choice = None
        # refresh UI immediately
        st.rerun()

st.markdown("---")

# --- Totals, percentages, progress bar ---
total_votes = st.session_state.yes + st.session_state.no

if total_votes > 0:
    yes_pct = (st.session_state.yes / total_votes) * 100
    no_pct = (st.session_state.no / total_votes) * 100

    st.subheader(f"📊 Total Votes: {total_votes}")
    # progress shows proportion of YES (0-100)
    st.progress(min(max(int(round(yes_pct)), 0), 100))
    st.write(f"✅ Yes: **{st.session_state.yes}** ({yes_pct:.1f}%)")
    st.write(f"❌ No: **{st.session_state.no}** ({no_pct:.1f}%)")
else:
    st.subheader("📊 No votes yet")

st.markdown("---")

# --- Feedback to the user about their vote state ---
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

# Optional debug (uncomment to inspect session_state)
# st.write(dict(st.session_state))