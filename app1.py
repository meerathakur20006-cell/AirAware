from datetime import datetime
import random

import pandas as pd
import plotly.express as px
import serial
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# --------------------------------------------------
# 1. PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="AirAware | Smart Indoor Environment",
    page_icon="🌿",
    layout="wide",
)


# --------------------------------------------------
# 2. SESSION DATA & SERIAL CONNECTION
# --------------------------------------------------

defaults = {
    "temperature": 28.0,
    "humidity": 55.0,
    "gas": 180,
    "history": [],
    "events": [],
    "actions": [],
    "previous_gas": None,
    "latest_event": None,
    "last_refresh_count": None,
    "monitoring_paused": False,
    "alert_sound_pending": False,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Initialize the serial connection once
if "serial_port" not in st.session_state:
    try:
        # REPLACE 'COM3' WITH YOUR ACTUAL PORT (e.g., 'COM4' or '/dev/ttyUSB0')
        st.session_state.serial_port = serial.Serial('COM3', 9600, timeout=1)
    except Exception as e:
        st.session_state.serial_port = None


# --------------------------------------------------
# 3. CUSTOM STYLING
# --------------------------------------------------

st.markdown("""
<style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    div[data-testid="stMetric"] {
        background-color: #e8f5ee;
        padding: 18px;
        border-radius: 12px;
        border: 1px solid #b7d9c6;
    }

    div[data-testid="stMetric"] label,
    div[data-testid="stMetric"] label p,
    div[data-testid="stMetric"] [data-testid="stMetricValue"],
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: #173d2b !important;
    }

    h1, h2, h3 {
        color: #246b4a;
    }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# 4. SIDEBAR AND NAVIGATION
# --------------------------------------------------

st.sidebar.title("🌿 AirAware")
st.sidebar.caption("Indoor Environment Intelligence")
st.sidebar.divider()

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Dashboard",
        "Smart Coach",
        "Pollution Detective",
        "Action Tracker",
        "Reports",
    ],
)

room = st.sidebar.selectbox(
    "Select room",
    ["Classroom", "Bedroom", "Office", "Laboratory"],
)

st.sidebar.divider()
st.sidebar.caption("Current mode: Live Hardware Integration")

if st.session_state.serial_port and st.session_state.serial_port.is_open:
    st.sidebar.success("🟢 Connected to hardware over USB")
else:
    st.sidebar.error("🔴 Hardware disconnected. Check COM port & close Arduino Serial Monitor.")


interval_seconds = st.sidebar.selectbox(
    "Automatic Reading Interval",
    options=[5, 10, 15, 30, 60],
    index=2,
    format_func=lambda seconds: f"Every {seconds} seconds",
)

if st.session_state.monitoring_paused:
    refresh_count = st.session_state.last_refresh_count or 0

    resume_monitoring = st.sidebar.button(
        "▶️ Resume Monitoring",
        type="primary",
    )

    manual_generate = False

    if resume_monitoring:
        st.session_state.monitoring_paused = False
        st.session_state.latest_event = None
        st.session_state.alert_sound_pending = False
        st.rerun()

else:
    refresh_count = st_autorefresh(
        interval=interval_seconds * 1000,
        key="airaware_refresh",
    )

    manual_generate = st.sidebar.button(
        "🔄 Read Hardware Now",
        type="primary",
    )

st.sidebar.caption(
    "Monitoring status: "
    + ("PAUSED — check the alert" if st.session_state.monitoring_paused
       else "ACTIVE")
)


# --------------------------------------------------
# 5. AUTOMATICALLY READ USB HARDWARE DATA
# --------------------------------------------------

should_generate = (
    not st.session_state.history
    or refresh_count != st.session_state.last_refresh_count
    or manual_generate
)

if should_generate:

    # Fallback to current values if reading fails
    new_temperature = st.session_state.temperature
    new_humidity = st.session_state.humidity
    new_gas = st.session_state.gas

    # Read live data from USB serial port
    if st.session_state.serial_port and st.session_state.serial_port.is_open:
        try:
            st.session_state.serial_port.reset_input_buffer()
            line = st.session_state.serial_port.readline().decode('utf-8').strip()

            if line and "," in line:
                parts = line.split(',')
                if len(parts) == 3:
                    new_temperature = float(parts[0])
                    new_humidity = float(parts[1])
                    new_gas = int(float(parts[2]))
        except Exception as e:
            st.sidebar.warning(f"Error reading USB: {e}")

    previous_gas = st.session_state.previous_gas

    st.session_state.temperature = new_temperature
    st.session_state.humidity = new_humidity
    st.session_state.gas = new_gas

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    st.session_state.history.append({
        "Time": current_time,
        "Room": room,
        "Temperature (°C)": new_temperature,
        "Humidity (%)": new_humidity,
        "Gas sensor response": new_gas,
    })

    # Check whether the latest reading triggers an event.
    st.session_state.latest_event = None

    event_message = None

    if new_gas >= 300:
        event_message = "High gas-sensor response"

    elif (
        previous_gas is not None
        and new_gas >= previous_gas * 1.5
    ):
        event_message = "Sudden increase in gas-sensor response"

    if event_message:
        event = {
            "Time": current_time,
            "Room": room,
            "Reading": new_gas,
            "Event": event_message,
        }

        st.session_state.events.append(event)
        st.session_state.latest_event = event

        # Pause automatic monitoring and request an alarm.
        st.session_state.monitoring_paused = True
        st.session_state.alert_sound_pending = True

    st.session_state.previous_gas = new_gas

    # Remember which automatic refresh was processed.
    st.session_state.last_refresh_count = refresh_count


# --------------------------------------------------
# 6. SHARED CURRENT READINGS AND ROOM SCORE
# --------------------------------------------------

temperature = st.session_state.temperature
humidity = st.session_state.humidity
gas = st.session_state.gas


# --------------------------------------------------
# LIVE SENSOR STATUS
# --------------------------------------------------

if st.session_state.monitoring_paused:
    sensor_status = "CRITICAL"
elif gas >= 70:
    sensor_status = "MODERATE"
else:
    sensor_status = "NORMAL"

temperature_penalty = min(abs(temperature - 25) * 3, 30)
humidity_penalty = min(abs(humidity - 50) * 0.5, 25)
gas_penalty = min(max(gas - 100, 0) * 0.1, 45)

room_score = round(
    max(
        0,
        100
        - temperature_penalty
        - humidity_penalty
        - gas_penalty,
    )
)

if room_score >= 80:
    score_label = "Favorable"
elif room_score >= 60:
    score_label = "Needs attention"
else:
    score_label = "Review room conditions"


# --------------------------------------------------
# 6A. GLOBAL ALERT AND SOUND
# --------------------------------------------------

if st.session_state.monitoring_paused:
    alert = st.session_state.latest_event

    st.error("🚨 AIRWARE ALERT: UNUSUAL SENSOR RESPONSE DETECTED")

    if alert:
        st.warning(
            f"{alert['Event']} | "
            f"Room: {alert['Room']} | "
            f"Sensor response: {alert['Reading']} | "
            f"Time: {alert['Time']}"
        )

    st.warning(
        "Automatic readings are paused. Check the room and "
        "investigate the possible cause before resuming monitoring."
    )

    if st.session_state.alert_sound_pending:
        st.components.v1.html(
            """
            <script>
            const AudioContextClass =
                window.AudioContext || window.webkitAudioContext;

            if (AudioContextClass) {
                const ctx = new AudioContextClass();

                ctx.resume().then(() => {
                    const oscillator = ctx.createOscillator();
                    const gain = ctx.createGain();

                    oscillator.type = "sine";
                    oscillator.frequency.value = 880;
                    gain.gain.value = 0.15;

                    oscillator.connect(gain);
                    gain.connect(ctx.destination);

                    oscillator.start();

                    setTimeout(() => {
                        oscillator.stop();
                        ctx.close();
                    }, 5000);
                }).catch(() => {
                    console.log("Browser blocked automatic audio.");
                });
            }
            </script>
            """,
            height=0,
        )

        st.session_state.alert_sound_pending = False

    st.info(
        "After checking the situation, use "
        "'Resume Monitoring' in the sidebar."
    )

    st.divider()


# --------------------------------------------------
# 7. DASHBOARD
# --------------------------------------------------

if page == "Dashboard":
    # Live Sensor Status Card
    st.subheader("🌡️ Live Sensor Status")

    if sensor_status == "NORMAL":
        st.success("🟢 NORMAL | Sensor response is within optimal range.")
        status_color = "#16a34a"

    elif sensor_status == "MODERATE":
        st.warning("🟠 MODERATE | Check the sensor response.")
        status_color = "#f59e0b"

    else:
        st.error("🔴 CRITICAL | Unusual response detected. Monitoring paused.")
        status_color = "#dc2626"

    st.markdown(
        f"""
        <div style="
            background-color: {status_color};
            color: white;
            padding: 14px;
            border-radius: 10px;
            text-align: center;
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 20px;
        ">
            AIRWARE STATUS: {sensor_status}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Monitoring Health Indicator
    st.subheader("📡 Monitoring Health")

    if st.session_state.monitoring_paused:
        st.error("⏸️ Monitoring Paused — Please review the alert.")
    else:
        st.success("🟢 Monitoring Active — Automatic readings enabled.")

    # Alert Severity Summary
    st.subheader("📊 Alert Summary")

    total_alerts = len(st.session_state.events)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Alerts", total_alerts)

    with col2:
        st.metric(
            "Current Severity",
            sensor_status,
        )

    with col3:
        st.metric(
            "Monitoring",
            "Paused" if st.session_state.monitoring_paused else "Active",
        )

    # Recent Alerts
    st.subheader("🚨 Recent Alerts")

    if st.session_state.events:
        recent_alerts = pd.DataFrame(
            st.session_state.events[-5:][::-1]
        )
        st.dataframe(
            recent_alerts,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No alerts recorded yet. AirAware is monitoring.")

    st.title("🌿 AirAware")
    st.subheader(f"{room} Overview")

    st.write(
        "Monitor indoor conditions, discover unusual changes, "
        "and get practical recommendations."
    )

    st.divider()
    st.subheader("🏠 Room Condition Score")

    score_col1, score_col2 = st.columns([1, 2])

    with score_col1:
        st.metric("Prototype Score", f"{room_score}/100")

    with score_col2:
        st.progress(room_score / 100)
        st.write(f"Status: **{score_label}**")

    st.caption(
        "This is an experimental score based on configured rules, "
        "not a certified indoor-air quality measurement."
    )

    st.divider()
    st.subheader("📍 Current Sensor Readings")

    col1, col2, col3 = st.columns(3)

    col1.metric("🌡️ Temperature", f"{temperature} °C")
    col2.metric("💧 Humidity", f"{humidity} %")
    col3.metric("🫧 Gas Sensor Response", gas)

    st.caption("Readings update automatically from your connected USB hardware.")

    st.divider()
    st.subheader("📈 Sensor History")

    if st.session_state.history:

        history_df = pd.DataFrame(st.session_state.history)

        temperature_chart = px.line(
            history_df,
            x="Time",
            y="Temperature (°C)",
            color="Room",
            markers=True,
            title="Temperature Over Time",
        )

        st.plotly_chart(
            temperature_chart,
            use_container_width=True,
        )

        humidity_chart = px.line(
            history_df,
            x="Time",
            y="Humidity (%)",
            color="Room",
            markers=True,
            title="Humidity Over Time",
        )

        st.plotly_chart(
            humidity_chart,
            use_container_width=True,
        )

        gas_chart = px.line(
            history_df,
            x="Time",
            y="Gas sensor response",
            color="Room",
            markers=True,
            title="Gas Sensor Response Over Time",
        )

        st.plotly_chart(
            gas_chart,
            use_container_width=True,
        )

        st.subheader("Recorded Readings")

        st.dataframe(
            history_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ Download Sensor History",
            data=history_df.to_csv(index=False).encode("utf-8"),
            file_name="airaware_sensor_history.csv",
            mime="text/csv",
        )

    else:
        st.info("No readings recorded yet.")


# --------------------------------------------------
# 8. SMART COACH
# --------------------------------------------------

elif page == "Smart Coach":

    st.title("🧠 AirAware Smart Coach")

    st.write(
        "Get practical suggestions based on the current "
        "temperature, humidity, and gas-sensor response."
    )

    col1, col2, col3 = st.columns(3)

    col1.metric("Temperature", f"{temperature} °C")
    col2.metric("Humidity", f"{humidity} %")
    col3.metric("Gas Response", gas)

    st.divider()
    st.subheader("💡 Your Recommendations")

    if gas >= 300:
        st.warning(
            "UNUSUAL GAS RESPONSE: Check for possible sources "
            "and improve ventilation if appropriate. The MQ-135 "
            "cannot identify a specific gas by itself."
        )
    else:
        st.success(
            "The configured high gas-response threshold has not "
            "been crossed. Continue monitoring; this does not "
            "confirm that the air is safe."
        )

    if humidity >= 70:
        st.warning(
            "HIGH HUMIDITY: Check for damp areas, condensation, "
            "and possible ventilation problems."
        )
    elif humidity < 35:
        st.info(
            "LOW HUMIDITY: Review room conditions and "
            "consider comfort needs."
        )
    else:
        st.info(
            "Humidity is within this prototype's configured "
            "comfort range."
        )

    if temperature >= 32:
        st.warning(
            "WARM ROOM: Consider improving airflow or adjusting "
            "the cooling system if appropriate."
        )
    elif temperature < 20:
        st.info(
            "COOL ROOM: Review the room temperature and "
            "adjust the environment if necessary."
        )
    else:
        st.info(
            "Temperature is within this prototype's configured "
            "comfort range."
        )

    st.divider()
    st.subheader("📋 Latest Detection")

    latest_event = st.session_state.latest_event

    if latest_event:
        st.error(
            f"{latest_event['Event']} — "
            f"Reading: {latest_event['Reading']}"
        )
    else:
        st.info(
            "No event was triggered by the latest reading. "
            "Hardware is active and monitoring."
        )

    st.caption(
        "Recommendations use prototype thresholds, not certified "
        "air-quality limits or medical advice."
    )


# --------------------------------------------------
# 9. POLLUTION DETECTIVE
# --------------------------------------------------

elif page == "Pollution Detective":

    st.title("🔎 AirAware Pollution Detective")

    st.write(
        "Investigate unusual sensor responses, record possible "
        "causes, and review recommended next steps."
    )

    st.warning(
        "The MQ-135 provides a broad sensor response. It cannot "
        "reliably identify the exact gas, pollutant, or cause."
    )

    latest_event = st.session_state.latest_event

    if latest_event:

        st.subheader("🚨 Automatic Detection")

        st.error(
            f"{latest_event['Event']} | "
            f"Reading: {latest_event['Reading']}"
        )

        st.caption(
            f"Detected at {latest_event['Time']} "
            f"in {latest_event['Room']}"
        )

        st.subheader("🔍 What might have caused it?")

        possible_cause = st.selectbox(
            "Select a possible activity or condition",
            [
                "Cooking or frying",
                "Cleaning sprays or products",
                "Smoke or fumes nearby",
                "Poor ventilation",
                "Many people in the room",
                "Other / Not sure",
            ],
            key="detective_cause",
        )

        advice = {
            "Cooking or frying": [
                "Use a suitable kitchen exhaust or range hood.",
                "Ventilate safely where possible.",
                "Compare later readings under similar conditions.",
            ],
            "Cleaning sprays or products": [
                "Follow the product label and safety instructions.",
                "Ventilate as directed by the product label.",
                "Never mix cleaning products.",
            ],
            "Smoke or fumes nearby": [
                "Move away from smoke or fumes.",
                "If safe, address the source and ventilate the area.",
                "If there may be a fire or a dangerous exposure, "
                "leave the area and seek appropriate help.",
            ],
            "Poor ventilation": [
                "Check whether safe ventilation is available.",
                "Open windows or doors if outdoor conditions permit.",
                "Compare readings after conditions change.",
            ],
            "Many people in the room": [
                "Consider improving ventilation if appropriate.",
                "Review whether readings change with occupancy.",
            ],
            "Other / Not sure": [
                "Review recent activities and possible sources.",
                "Compare the response with earlier readings.",
                "If unusual conditions persist, seek further "
                "assessment instead of assuming the air is safe.",
            ],
        }

        st.subheader("💡 Recommended Actions")

        for item in advice[possible_cause]:
            st.info("➡️ " + item)

    else:
        st.info(
            "The latest reading has not triggered a detection event. "
            "Hardware is currently sending normal readings. "
            "Previous events remain in the history."
        )

    st.divider()
    st.subheader("📋 Detection History")

    if st.session_state.events:

        events_df = pd.DataFrame(st.session_state.events)

        st.dataframe(
            events_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ Download Detection History",
            data=events_df.to_csv(index=False).encode("utf-8"),
            file_name="airaware_detection_events.csv",
            mime="text/csv",
        )

    else:
        st.info("No detection events have been recorded yet.")


# --------------------------------------------------
# 10. VENTILATION ACTION TRACKER
# --------------------------------------------------

elif page == "Action Tracker":

    st.title("🪟 Ventilation Action Tracker")

    st.write(
        "Record an action, then capture a follow-up reading "
        "to compare the sensor response."
    )

    st.metric("Current Gas-Sensor Response", gas)

    st.subheader("Step 1 — Record Your Action")

    action_type = st.selectbox(
        "Action performed",
        [
            "Opened a window",
            "Turned on ventilation",
            "Turned on an air purifier",
            "Removed a possible pollutant source",
            "Other",
        ],
        key="action_type",
    )

    notes = st.text_input(
        "Notes (optional)",
        placeholder="Example: Opened classroom windows",
        key="action_notes",
    )

    if st.button("Record Action", type="primary"):

        st.session_state.actions.append({
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Room": room,
            "Action": action_type,
            "Notes": notes,
            "Before response": gas,
            "After response": None,
            "Change (%)": None,
        })

        st.success(
            "Action recorded. After allowing time for conditions "
            "to change, click Read Hardware Now in the sidebar before "
            "capturing the follow-up."
        )

    st.divider()
    st.subheader("Step 2 — Capture a Follow-up Reading")

    pending_actions = [
        i
        for i, action in enumerate(st.session_state.actions)
        if action["After response"] is None
    ]

    if pending_actions:

        action_labels = {
            i: (
                f'{i + 1}. {st.session_state.actions[i]["Action"]} '
                f'({st.session_state.actions[i]["Time"]})'
            )
            for i in pending_actions
        }

        selected_action = st.selectbox(
            "Select an action to evaluate",
            options=pending_actions,
            format_func=lambda i: action_labels[i],
            key="selected_action",
        )

        selected_record = st.session_state.actions[selected_action]

        st.write(
            f"Original response: {selected_record['Before response']} "
            f"| Current response: {gas}"
        )

        if st.button("Capture Follow-up Reading"):

            action = st.session_state.actions[selected_action]

            before = action["Before response"]
            after = gas

            action["After response"] = after

            if before != 0:
                change = ((after - before) / before) * 100
                action["Change (%)"] = round(change, 1)
            else:
                action["Change (%)"] = None

            st.success("Follow-up reading recorded.")

    else:
        st.info(
            "Record an action first, or all recorded actions "
            "already have follow-up readings."
        )

    st.divider()
    st.subheader("Action History and Comparison")

    if st.session_state.actions:

        actions_df = pd.DataFrame(st.session_state.actions)

        st.dataframe(
            actions_df,
            use_container_width=True,
            hide_index=True,
        )

        completed_actions = [
            action
            for action in st.session_state.actions
            if action["After response"] is not None
        ]

        if completed_actions:

            latest = completed_actions[-1]

            st.subheader("Latest Before-and-After Comparison")

            before_col, after_col, change_col = st.columns(3)

            before_col.metric(
                "Before Action",
                latest["Before response"],
            )

            after_col.metric(
                "After Action",
                latest["After response"],
            )

            change = latest["Change (%)"]

            if change is not None:
                change_col.metric(
                    "Change in Response",
                    f"{change:+.1f}%",
                )
            else:
                change_col.metric(
                    "Change in Response",
                    "Unavailable",
                )

            st.caption(
                "A lower response does not prove that the air is "
                "safe or that a particular pollutant decreased. "
                "Sensor readings can vary with several conditions."
            )

        st.download_button(
            "⬇️ Download Action History",
            data=actions_df.to_csv(index=False).encode("utf-8"),
            file_name="airaware_action_history.csv",
            mime="text/csv",
        )

    else:
        st.info("No actions recorded yet.")


# --------------------------------------------------
# 11. REPORTS
# --------------------------------------------------

elif page == "Reports":

    st.title("📊 AirAware Reports")

    st.write(
        "Review sensor readings, unusual events, and recorded "
        "ventilation actions from this session."
    )

    readings_df = pd.DataFrame(st.session_state.history)
    events_df = pd.DataFrame(st.session_state.events)
    actions_df = pd.DataFrame(st.session_state.actions)

    col1, col2, col3 = st.columns(3)

    col1.metric("Readings Collected", len(readings_df))
    col2.metric("Unusual Events", len(events_df))
    col3.metric("Actions Recorded", len(actions_df))

    st.divider()
    st.subheader("📈 Reading Summary")

    if not readings_df.empty:

        summary = readings_df[
            [
                "Temperature (°C)",
                "Humidity (%)",
                "Gas sensor response",
            ]
        ].agg(["min", "mean", "max"]).round(2)

        st.dataframe(
            summary,
            use_container_width=True,
        )

        st.subheader("All Sensor Readings")

        st.dataframe(
            readings_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ Download All Sensor Readings",
            data=readings_df.to_csv(index=False).encode("utf-8"),
            file_name="airaware_readings.csv",
            mime="text/csv",
        )

    else:
        st.info(
            "No sensor readings available yet."
        )

    st.divider()
    st.subheader("🚨 Event Summary")

    if not events_df.empty:

        st.dataframe(
            events_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ Download Event Report",
            data=events_df.to_csv(index=False).encode("utf-8"),
            file_name="airaware_events.csv",
            mime="text/csv",
        )

    else:
        st.info("No unusual events have been recorded.")

    st.divider()
    st.subheader("🪟 Action Summary")

    if not actions_df.empty:

        st.dataframe(
            actions_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ Download Action Report",
            data=actions_df.to_csv(index=False).encode("utf-8"),
            file_name="airaware_actions.csv",
            mime="text/csv",
        )

    else:
        st.info("No actions have been recorded.")

    st.caption(
        "Reports summarize this Streamlit session. Permanent "
        "database storage can be added later."
    )


# --------------------------------------------------
# 12. FOOTER
# --------------------------------------------------

st.divider()

st.caption(
    "AirAware | Indoor Environment Intelligence | "
    "Connected Hardware Integration"
)