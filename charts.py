import json
import re
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

def render_dynamic_chart_from_text(response_text: str):
    """
    Parses LLM response text for embedded JSON chart data, renders the markdown text, 
    and generates an interactive Plotly chart with a cyberpunk aesthetic.
    """
    if not response_text:
        return

    # 1. Regex to find JSON block embedded within ```json ... ``` tags
    json_pattern = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)
    match = json_pattern.search(response_text)

    if match:
        json_str = match.group(1)
        
        # 2. Clean the raw JSON out of the main text string
        clean_text = response_text.replace(match.group(0), "").strip()
        
        # 3. Render the standard text markdown first
        if clean_text:
            st.markdown(clean_text)

        # 4. Extract and render the chart
        try:
            chart_data = json.loads(json_str)
            
            chart_type = chart_data.get("type", "").lower()
            title = chart_data.get("title", "Data Visualization")
            x_vals = chart_data.get("x", [])
            y_vals = chart_data.get("y", [])
            x_label = chart_data.get("x_label", "X Axis")
            y_label = chart_data.get("y_label", "Y Axis")

            # Validate basic data integrity
            if not x_vals or not y_vals or len(x_vals) != len(y_vals):
                raise ValueError("Invalid or mismatched X and Y data arrays.")

            fig = None
            
            # Neon Cyberpunk Color Palette
            cyber_color = "#f97316" # Matches your APOLLO primary orange
            
            if chart_type == "bar":
                fig = px.bar(x=x_vals, y=y_vals, title=title, labels={"x": x_label, "y": y_label})
                fig.update_traces(marker_color=cyber_color, marker_line_color="#ea580c", marker_line_width=1.5)
            
            elif chart_type == "line":
                fig = px.line(x=x_vals, y=y_vals, title=title, labels={"x": x_label, "y": y_label})
                fig.update_traces(line=dict(color=cyber_color, width=3), mode='lines+markers', marker=dict(size=8, color="#38bdf8"))
            
            elif chart_type == "pie":
                fig = px.pie(names=x_vals, values=y_vals, title=title)
                # Apply a custom cyberpunk sequential color scale for pies
                fig.update_traces(marker=dict(colors=["#f97316", "#38bdf8", "#4ade80", "#eab308", "#d946ef"], line=dict(color='#0f0f11', width=2)))
            else:
                raise ValueError(f"Unsupported chart type: {chart_type}")

            # Apply Dark/Cyberpunk Theme Styling
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="JetBrains Mono, monospace", color="#e5e7eb"),
                title=dict(font=dict(size=20, color="#f97316")),
                xaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(255,255,255,0.1)"),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(255,255,255,0.1)"),
                margin=dict(l=40, r=40, t=60, b=40)
            )

            # Render interactive Plotly chart
            st.plotly_chart(fig, use_container_width=True)

        except (json.JSONDecodeError, ValueError, Exception) as e:
            # 5. Graceful Error Handling: If JSON fails, render standard code block
            st.warning(f"⚠️ Could not render interactive chart. Raw data below.")
            st.code(json_str, language="json")
            
    else:
        # No JSON block found, just render the standard markdown
        st.markdown(response_text)
