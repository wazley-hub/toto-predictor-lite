import base64
import hmac
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components


APP_DIR = Path(__file__).resolve().parent
LOCAL_DATA = APP_DIR / "TotoHistoryAll.xlsx"
GITHUB_OWNER = "wazley-hub"
GITHUB_REPO = "toto-predictor-lite"
GITHUB_BRANCH = "main"
GITHUB_DATA_PATH = "TotoHistoryAll.xlsx"
GITHUB_CONTENTS_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/"
    f"{GITHUB_DATA_PATH}"
)


st.set_page_config(page_title="Toto Predictor", page_icon="🎯", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 4rem; max-width: 1180px;}
    h1, h2, h3 {letter-spacing: -0.02em;}
    div[data-testid="stMetric"] {
        border: 1px solid #e5e7eb; border-radius: 12px; padding: 12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def pad4(value):
    try:
        if pd.isna(value):
            return "0000"
    except Exception:
        pass
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(4)[-4:]


def family4(value):
    return "".join(sorted(pad4(value)))


def normalize_history(df):
    aliases = {
        "DrawNo": "draw_no",
        "DrawDate": "draw_date",
        "1stPrizeNo": "first",
        "2ndPrizeNo": "second",
        "3rdPrizeNo": "third",
    }
    missing = [column for column in aliases if column not in df.columns]
    if missing:
        raise ValueError("Format data tidak lengkap.")
    out = df[list(aliases)].rename(columns=aliases).copy()
    for column in ("first", "second", "third"):
        out[column] = out[column].map(pad4)
    return out.reset_index(drop=True)


def get_secret(name):
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def github_headers(token=""):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_github_workbook(token=""):
    response = requests.get(
        GITHUB_CONTENTS_API,
        params={"ref": GITHUB_BRANCH},
        headers=github_headers(token),
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    encoded = str(payload.get("content", "")).replace("\n", "")
    if not encoded:
        raise RuntimeError("Kandungan fail GitHub tidak dapat dibaca.")
    return base64.b64decode(encoded), str(payload.get("sha", ""))


@st.cache_data(ttl=60, show_spinner=False)
def load_history():
    try:
        workbook_bytes, _ = fetch_github_workbook(get_secret("LITE_GITHUB_TOKEN"))
        return (
            normalize_history(pd.read_excel(BytesIO(workbook_bytes))),
            "GitHub Toto Predictor Lite",
        )
    except Exception:
        if not LOCAL_DATA.exists():
            raise RuntimeError("Data GitHub tidak dapat dibaca dan fail fallback tiada.")
        return normalize_history(pd.read_excel(LOCAL_DATA)), "Fail fallback (read-only)"


def validate_update(raw_df, draw_no, draw_date, first, second, third):
    values = (first, second, third)
    if not draw_no.isdigit():
        return "Draw No mesti mengandungi nombor sahaja."
    if not draw_date.isdigit() or len(draw_date) != 8:
        return "Tarikh mesti dalam format YYYYMMDD, contohnya 20260725."
    try:
        datetime.strptime(draw_date, "%Y%m%d")
    except ValueError:
        return "Tarikh tidak sah."
    if not all(value.isdigit() and len(value) == 4 for value in values):
        return "1st, 2nd dan 3rd Prize mesti tepat empat digit."

    existing_draws = raw_df["DrawNo"].astype(str).str.replace(r"\.0$", "", regex=True)
    if draw_no in set(existing_draws):
        return f"Draw {draw_no} sudah wujud. Kemas kini dibatalkan."

    dates = pd.to_numeric(raw_df["DrawDate"], errors="coerce").dropna()
    if not dates.empty and int(draw_date) <= int(dates.max()):
        return "Tarikh baharu mesti selepas tarikh keputusan terakhir."
    return ""


def update_github_history(draw_no, draw_date, first, second, third):
    token = get_secret("LITE_GITHUB_TOKEN")
    if not token:
        raise RuntimeError("LITE_GITHUB_TOKEN belum ditetapkan dalam Streamlit Secrets.")

    workbook_bytes, current_sha = fetch_github_workbook(token)
    raw_df = pd.read_excel(BytesIO(workbook_bytes))
    required = ["DrawNo", "DrawDate", "1stPrizeNo", "2ndPrizeNo", "3rdPrizeNo"]
    if any(column not in raw_df.columns for column in required):
        raise RuntimeError("Format TotoHistoryAll.xlsx dalam repo tidak sah.")

    validation_error = validate_update(
        raw_df, draw_no, draw_date, first, second, third
    )
    if validation_error:
        raise ValueError(validation_error)

    new_row = {
        "DrawNo": int(draw_no),
        "DrawDate": int(draw_date),
        "1stPrizeNo": int(first),
        "2ndPrizeNo": int(second),
        "3rdPrizeNo": int(third),
    }
    updated = pd.concat([raw_df, pd.DataFrame([new_row])], ignore_index=True)
    output = BytesIO()
    updated.to_excel(output, index=False, engine="openpyxl")

    response = requests.put(
        GITHUB_CONTENTS_API,
        headers=github_headers(token),
        json={
            "message": f"Update Toto Predictor Lite Draw {draw_no}",
            "content": base64.b64encode(output.getvalue()).decode("ascii"),
            "sha": current_sha,
            "branch": GITHUB_BRANCH,
        },
        timeout=30,
    )
    response.raise_for_status()


def copy_button(label, value, key):
    import json

    payload = json.dumps(str(value))
    components.html(
        f"""
        <button onclick='navigator.clipboard.writeText({payload}).then(() => {{
            const msg = document.getElementById("msg_{key}");
            msg.innerText = "Disalin";
            setTimeout(() => msg.innerText = "", 1500);
        }})'
        style="border:0;border-radius:10px;background:#2563eb;color:white;
               padding:10px 16px;font-size:15px;font-weight:700;cursor:pointer;">
            {label}
        </button>
        <span id="msg_{key}" style="color:#15803d;font-size:14px;font-weight:600;margin-left:8px;"></span>
        """,
        height=48,
    )


def build_bridge_v1(first, second, third):
    numbers = [pad4(first), pad4(second), pad4(third)]
    existing = sorted(set("".join(numbers)))
    missing = sorted(set("0123456789") - set(existing))
    pair_rows = []
    base_pairs = []
    for source, number in zip(("1st", "2nd", "3rd"), numbers):
        for position, pair in zip(
            ("Front", "Middle", "Back"),
            (number[:2], number[1:3], number[2:4]),
        ):
            pair_rows.append(
                {"Source": source, "Pair Position": position, "Pair": pair}
            )
            base_pairs.append(pair)
    base_pairs = list(dict.fromkeys(base_pairs))

    rows = []
    seen = set()
    for pair in base_pairs:
        for missing_digit in missing:
            for existing_digit in existing:
                number = f"{pair}{missing_digit}{existing_digit}"
                family = family4(number)
                if family in seen:
                    continue
                seen.add(family)
                rows.append({"No": number, "Family": family, "Base Pair": pair})
    bridge_df = pd.DataFrame(rows, columns=["No", "Family", "Base Pair"])
    text = (
        "🧪 Toto Predictor - Bridge V1\n\n"
        f"Base Pairs:\n{' / '.join(base_pairs)}\n\n"
        f"Missing Digits:\n{' / '.join(missing)}\n\n"
        f"Existing Digits:\n{' / '.join(existing)}\n\n"
        f"Bridge Numbers (Total: {len(bridge_df)}):\n"
    )
    values = bridge_df["No"].tolist()
    text += "\n".join(
        " / ".join(values[index:index + 10])
        for index in range(0, len(values), 10)
    ) or "Tiada output."
    return pd.DataFrame(pair_rows), bridge_df, text


@st.cache_data(show_spinner=False)
def build_pair_priority(history, first, second, third):
    slots = [
        ("1st", "Front", 0, "first"),
        ("1st", "Middle", 1, "first"),
        ("1st", "Back", 2, "first"),
        ("2nd", "Front", 0, "second"),
        ("2nd", "Middle", 1, "second"),
        ("2nd", "Back", 2, "second"),
        ("3rd", "Front", 0, "third"),
        ("3rd", "Middle", 1, "third"),
        ("3rd", "Back", 2, "third"),
    ]
    v1_hits = Counter()
    transitions = len(history) - 1
    for index in range(transitions):
        source_numbers = [
            pad4(history.iloc[index][column])
            for column in ("first", "second", "third")
        ]
        existing = sorted(set("".join(source_numbers)))
        missing = sorted(set("0123456789") - set(existing))
        targets = {
            family4(history.iloc[index + 1][column])
            for column in ("first", "second", "third")
        }
        for source, position, start, column in slots:
            pair = pad4(history.iloc[index][column])[start:start + 2]
            v1_families = {
                family4(f"{pair}{missing_digit}{existing_digit}")
                for missing_digit in missing
                for existing_digit in existing
            }
            if v1_families & targets:
                v1_hits[(source, position)] += 1

    current = {"first": pad4(first), "second": pad4(second), "third": pad4(third)}
    rows = []
    for order, (source, position, start, column) in enumerate(slots):
        v1 = int(v1_hits[(source, position)])
        rows.append(
            {
                "Source": source,
                "Pair Position": position,
                "Current Pair": current[column][start:start + 2],
                "Historical Hit": v1,
                "Transitions": transitions,
                "_Order": order,
            }
        )
    ranked = pd.DataFrame(rows).sort_values(
        ["Historical Hit", "_Order"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    ranked.insert(0, "Priority", range(1, len(ranked) + 1))
    return ranked.drop(columns="_Order")


def build_pair_numbers(pair, audit_row, first, second, third):
    current = [pad4(first), pad4(second), pad4(third)]
    existing = sorted(set("".join(current)))
    missing = sorted(set("0123456789") - set(existing))
    pair = str(pair).zfill(2)[-2:]
    records = {}

    def add(number, route):
        family = family4(number)
        records.setdefault(
            (route, family),
            {"Pair": pair, "No": number, "Family": family, "Route": route},
        )

    for missing_digit in missing:
        for existing_digit in existing:
            add(f"{pair}{missing_digit}{existing_digit}", "Bridge V1")
    frame = pd.DataFrame(
        records.values(), columns=["Pair", "No", "Family", "Route"]
    )
    lines = [
        "🧭 Toto Predictor - Bridge Pair Shortlist",
        "",
        f"Pair Pilihan: {pair}",
        f'Sumber Ranking: {audit_row["Source"]} Prize - {audit_row["Pair Position"]}',
        f'Historical Hit: {int(audit_row["Historical Hit"])}',
    ]
    values = frame["No"].tolist()
    lines.extend(["", f"Bridge V1 (Pilihan Unik: {len(values)}):"])
    lines.extend(
        " / ".join(values[index:index + 10])
        for index in range(0, len(values), 10)
    )
    return frame, "\n".join(lines)


st.title("🎯 Toto Predictor")
st.caption("Bridge Analysis Lite")

try:
    history, data_source = load_history()
except Exception as error:
    st.error(str(error))
    st.stop()

latest = history.iloc[-1]
st.subheader("📅 Keputusan Terbaru")
result_columns = st.columns(4)
result_columns[0].metric("Draw No", str(latest["draw_no"]))
result_columns[1].metric("1st Prize", pad4(latest["first"]))
result_columns[2].metric("2nd Prize", pad4(latest["second"]))
result_columns[3].metric("3rd Prize", pad4(latest["third"]))
st.caption(f'Tarikh: {latest["draw_date"]}')

with st.expander("📝 Update Keputusan", expanded=False):
    update_password = st.text_input(
        "Kata laluan kemas kini",
        type="password",
        key="lite_update_password_input",
    )
    update_columns = st.columns(2)
    new_draw_no = update_columns[0].text_input(
        "Draw No baharu", key="lite_new_draw_no"
    ).strip()
    new_draw_date = update_columns[1].text_input(
        "Tarikh baharu (YYYYMMDD)", key="lite_new_draw_date", max_chars=8
    ).strip()
    prize_columns = st.columns(3)
    new_first = prize_columns[0].text_input(
        "1st Prize baharu", key="lite_new_first", max_chars=4
    ).strip()
    new_second = prize_columns[1].text_input(
        "2nd Prize baharu", key="lite_new_second", max_chars=4
    ).strip()
    new_third = prize_columns[2].text_input(
        "3rd Prize baharu", key="lite_new_third", max_chars=4
    ).strip()
    confirm_update = st.checkbox(
        "Saya telah menyemak dan mengesahkan keputusan ini.",
        key="lite_confirm_update",
    )

    if st.button("Simpan Keputusan", key="lite_save_result"):
        configured_password = get_secret("LITE_UPDATE_PASSWORD")
        if not configured_password:
            st.error("LITE_UPDATE_PASSWORD belum ditetapkan dalam Streamlit Secrets.")
        elif not hmac.compare_digest(update_password, configured_password):
            st.error("Kata laluan kemas kini salah.")
        elif not confirm_update:
            st.error("Tandakan kotak pengesahan sebelum menyimpan.")
        else:
            try:
                with st.spinner("Menyimpan keputusan ke repo Lite..."):
                    update_github_history(
                        new_draw_no,
                        new_draw_date,
                        new_first,
                        new_second,
                        new_third,
                    )
                load_history.clear()
                st.success(f"Draw {new_draw_no} berjaya disimpan.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
            except requests.HTTPError as error:
                status = getattr(error.response, "status_code", "")
                st.error(
                    f"GitHub menolak kemas kini ({status}). "
                    "Semak token dan akses repo Lite."
                )
            except Exception as error:
                st.error(f"Kemas kini gagal: {error}")

st.divider()
st.subheader("🎲 Generate")
input_columns = st.columns(3)
first = input_columns[0].text_input("1st Prize", value=pad4(latest["first"]), max_chars=4)
second = input_columns[1].text_input("2nd Prize", value=pad4(latest["second"]), max_chars=4)
third = input_columns[2].text_input("3rd Prize", value=pad4(latest["third"]), max_chars=4)

if st.button("Generate", type="primary"):
    if not all(value.isdigit() and len(value) == 4 for value in (first, second, third)):
        st.error("Masukkan tepat empat digit untuk setiap keputusan.")
    else:
        st.session_state["generated_values"] = (first, second, third)

if "generated_values" not in st.session_state:
    st.stop()

first, second, third = st.session_state["generated_values"]

st.divider()
st.subheader("🧪 Bridge V1")
pair_df, bridge_df, bridge_text = build_bridge_v1(first, second, third)
st.caption(f"Jumlah pilihan unik: {len(bridge_df)}")
copy_button("📋 Copy Bridge V1", bridge_text, "bridge_v1")
with st.expander("Lihat Detail Bridge V1", expanded=False):
    st.markdown("**Base Pair**")
    st.dataframe(pair_df, hide_index=True, use_container_width=True)
    st.markdown("**Senarai Bridge**")
    st.dataframe(
        bridge_df.drop(columns=["Family"], errors="ignore"),
        hide_index=True,
        use_container_width=True,
    )

st.subheader("🧭 Bridge Pair Shortlist")
st.caption(
    "Pair disusun mengikut jumlah hit sejarah Bridge V1. Buka mana-mana pair "
    "untuk melihat nombor Bridge V1 bagi pair itu sahaja."
)
priority_df = build_pair_priority(history, first, second, third)
ranking = " / ".join(
    f'#{int(row["Priority"])} {row["Current Pair"]}'
    for _, row in priority_df.iterrows()
)
st.markdown(f"**Ranking Pair:** {ranking}")

shown = set()
for _, audit_row in priority_df.iterrows():
    pair = str(audit_row["Current Pair"]).zfill(2)[-2:]
    if pair in shown:
        continue
    shown.add(pair)
    numbers_df, copy_text = build_pair_numbers(
        pair, audit_row, first, second, third
    )
    same_pair = priority_df[
        priority_df["Current Pair"].astype(str).str.zfill(2) == pair
    ]
    source_text = " / ".join(
        f'{row["Source"]} {row["Pair Position"]}'
        for _, row in same_pair.iterrows()
    )
    label = (
        f'#{int(audit_row["Priority"])} Pair {pair} · '
        f'Hit {int(audit_row["Historical Hit"])}'
    )
    with st.expander(label, expanded=False):
        st.caption(
            f'Sumber: {source_text} · '
            f'Historical Hit: {int(audit_row["Historical Hit"])}'
        )
        copy_button(f"📋 Copy Pair {pair}", copy_text, f"pair_{pair}")
        st.markdown(f"**Bridge V1 — {len(numbers_df)} pilihan unik**")
        st.dataframe(
            numbers_df.drop(columns=["Family"], errors="ignore"),
            hide_index=True,
            use_container_width=True,
        )

with st.expander("Lihat audit sembilan kedudukan pair", expanded=False):
    st.dataframe(priority_df, hide_index=True, use_container_width=True)
