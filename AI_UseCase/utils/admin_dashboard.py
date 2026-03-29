from __future__ import annotations

import pandas as pd
import streamlit as st

from db.database import list_bookings


def render_admin_dashboard() -> None:
    st.subheader("Admin Dashboard")
    st.caption("View and filter stored bookings.")

    col1, col2, col3 = st.columns(3)
    with col1:
        name_filter = st.text_input("Filter by name")
    with col2:
        email_filter = st.text_input("Filter by email")
    with col3:
        date_filter = st.text_input("Filter by date (YYYY-MM-DD)")

    rows = list_bookings(
        name=name_filter.strip() or None,
        email=email_filter.strip() or None,
        date=date_filter.strip() or None,
    )

    if not rows:
        st.info("No bookings found.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
