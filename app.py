import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime, date, time as time_type
from zoneinfo import ZoneInfo

st.set_page_config(layout="wide")

IST = ZoneInfo("Asia/Kolkata")

CP_NAMES = ["Tushita", "Ayushi", "Christina", "Deshna", "Nikita", "Upasha", "Anarghya"]
TIME_SLOTS = [time_type(h, m) for h in range(8, 20) for m in (0, 30)] + [time_type(20, 0)]


@st.cache_resource
def get_supabase():
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])


@st.cache_data(ttl=30)
def load_cases():
    result = get_supabase().table("cases").select("*").order("allotment_datetime").execute()
    if not result.data:
        return pd.DataFrame(columns=["cp_name", "case_description", "alloted_by", "announced_by", "allotment_datetime", "notes"])
    df = pd.DataFrame(result.data)
    df["allotment_datetime"] = pd.to_datetime(df["allotment_datetime"], format="ISO8601", utc=True).dt.tz_convert("Asia/Kolkata")
    return df


def get_roster_queue():
    df = load_cases()
    last_case = df.groupby("cp_name")["allotment_datetime"].max() if not df.empty else pd.Series(dtype="object")
    total = df.groupby("cp_name").size() if not df.empty else pd.Series(dtype="int")
    no_cases = [cp for cp in CP_NAMES if cp not in last_case.index]
    has_cases = last_case.sort_values().index.tolist()
    queue = no_cases + has_cases
    last_map = last_case.dt.strftime("%-d %b %Y, %I:%M %p").to_dict() if not last_case.empty else {}
    return pd.DataFrame({
        "#": range(1, len(queue) + 1),
        "CP": queue,
        "Total": [int(total.get(cp, 0)) for cp in queue],
        "Last Case": [last_map.get(cp, "—") for cp in queue],
    })


def check_password():
    if st.session_state.get("authenticated"):
        return True

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.title("CaseLog")
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True):
                users = st.secrets["users"]
                if username in users and users[username] == password:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Invalid credentials")
    return False


def log_case_tab():
    if st.session_state.get("last_success"):
        st.success(st.session_state.pop("last_success"))

    form_col, roster_col = st.columns(2)

    with roster_col:
        st.markdown("**Roster Queue**")
        st.dataframe(get_roster_queue(), hide_index=True, use_container_width=True)

    with form_col:
        cp_name = st.selectbox("CP Name *", CP_NAMES, key="f_cp")
        case_description = st.text_input("Case / Assessment *", key="f_case")
        alloted_by = st.radio("Alloted By *", ["Senior", "Faculty"], horizontal=True, key="f_alloted_by")
        announced_by = st.text_input("Announced By (optional)", key="f_announced")
        col1, col2 = st.columns(2)
        with col1:
            allotment_date = st.date_input("Allotment Date", value=date.today(), key="f_date")
        with col2:
            allotment_time = st.selectbox("Allotment Time", TIME_SLOTS, format_func=lambda t: t.strftime("%I:%M %p"), key="f_time")
        notes = st.text_area("Notes (optional)", key="f_notes")

        if st.button("Submit", type="primary", use_container_width=True):
            if not case_description.strip():
                st.error("Case / Assessment is required.")
            else:
                allotment_datetime = datetime.combine(allotment_date, allotment_time, tzinfo=IST)
                get_supabase().table("cases").insert({
                    "cp_name": cp_name,
                    "case_description": case_description.strip(),
                    "alloted_by": alloted_by,
                    "announced_by": announced_by.strip() or None,
                    "allotment_datetime": allotment_datetime.isoformat(),
                    "notes": notes.strip() or None,
                }).execute()
                load_cases.clear()
                st.session_state.last_success = f"Case logged for {cp_name}!"
                for k in ["f_cp", "f_case", "f_alloted_by", "f_announced", "f_notes", "f_time", "f_date"]:
                    st.session_state.pop(k, None)
                st.rerun()


def all_cases_tab():
    df = load_cases()
    if df.empty:
        st.info("No cases logged yet.")
        return

    display = df[["allotment_datetime", "cp_name", "case_description", "alloted_by", "announced_by", "notes"]].copy()
    display["allotment_datetime"] = display["allotment_datetime"].dt.strftime("%-d %b %Y, %I:%M %p")
    display.columns = ["Date & Time", "CP Name", "Case / Assessment", "Alloted By", "Announced By", "Notes"]
    st.dataframe(display, use_container_width=True, hide_index=True)


def analytics_tab():
    df = load_cases()
    if df.empty:
        st.info("No cases logged yet.")
        return

    all_cps = pd.DataFrame({"cp_name": CP_NAMES})

    months = df["allotment_datetime"].dt.to_period("M").unique()
    months = sorted(months, reverse=True)
    selected = st.selectbox("Month", [str(m) for m in months])

    month_df = df[df["allotment_datetime"].dt.to_period("M") == selected]
    monthly = month_df.groupby("cp_name").size().reset_index(name="Cases")
    monthly = all_cps.merge(monthly, on="cp_name", how="left").fillna(0)
    monthly["Cases"] = monthly["Cases"].astype(int)
    monthly = monthly.sort_values("Cases", ascending=False).rename(columns={"cp_name": "CP Name"})

    st.subheader(f"Cases in {selected}")
    st.dataframe(monthly, use_container_width=True, hide_index=True)

    st.divider()

    leaderboard = df.groupby("cp_name").size().reset_index(name="Total Cases")
    leaderboard = all_cps.merge(leaderboard, on="cp_name", how="left").fillna(0)
    leaderboard["Total Cases"] = leaderboard["Total Cases"].astype(int)
    leaderboard = leaderboard.sort_values("Total Cases", ascending=False).reset_index(drop=True)
    leaderboard.insert(0, "Rank", range(1, len(leaderboard) + 1))
    leaderboard = leaderboard.rename(columns={"cp_name": "CP Name"})

    st.subheader("All-Time Leaderboard")
    st.dataframe(leaderboard, use_container_width=True, hide_index=True)


if not check_password():
    st.stop()

st.title("CaseLog")
tab1, tab2, tab3 = st.tabs(["Log Case", "All Cases", "Analytics"])
with tab1:
    log_case_tab()
with tab2:
    all_cases_tab()
with tab3:
    analytics_tab()
