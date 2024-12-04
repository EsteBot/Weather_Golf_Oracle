import datetime as dt  
import pandas as pd
import plotly.express as px
import streamlit as st
import requests
import pytz
from pytz import timezone 
from datetime import datetime, timedelta

headers = {
    "authorization": st.secrets["Tomorrow_API_KEY"]
}

# Define the MST timezone
mst = timezone('US/Mountain')

# Function to get weather data
def get_weather_forecast(city = 'Denver'):
    url = f"https://api.tomorrow.io/v4/timelines"
    params = {
        "location": f"{city}",
        "fields": ["temperature", "temperatureMax", "precipitationProbability", "windSpeed", 
                    "sunriseTime", "sunsetTime"],
        "units": "imperial",
        "timesteps": ["1d", "1h"],
        "apikey": API_KEY,
        "startTime": dt.datetime.now(dt.timezone.utc).isoformat(),
        "endTime": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=4)).isoformat(),
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        st.error("Failed to fetch weather data")
        return None
    
def filter_forecast_by_sunrise_sunset(hourly_forecast, sunrise_time, sunset_time):
    # Convert to datetime objects for today's sunrise and sunset
    
    sunrise_dt_utc = dt.datetime.fromisoformat(sunrise_time[:-1])
    sunset_dt_utc = dt.datetime.fromisoformat(sunset_time[:-1])
    
    # Define the UTC and MST time zones
    utc = pytz.utc
    mst = pytz.timezone('US/Mountain')

    # Localize the datetime objects to UTC
    sunrise_dt_utc = utc.localize(sunrise_dt_utc)
    sunset_dt_utc = utc.localize(sunset_dt_utc)
    

    # Extract only the time part for sunrise and sunset in MST
    sunrise_time_only = sunrise_dt_utc.astimezone(mst).time()
    sunset_time_only = sunset_dt_utc.astimezone(mst).time()

    # Filter the forecast data
    filtered_forecast = []

    for hour in hourly_forecast:
        # Convert 'startTime' to a UTC datetime object first
        forecast_time_utc = dt.datetime.fromisoformat(hour["startTime"][:-1])
        forecast_time_utc = utc.localize(forecast_time_utc)

        # Convert the UTC datetime object to MST
        forecast_time_mst = forecast_time_utc.astimezone(mst)
        
        # Extract the date part of the forecast time
        forecast_date = forecast_time_mst.date()
        
        # Create new datetime objects for sunrise and sunset on the forecast date
        sunrise_dt_mst = dt.datetime.combine(forecast_date, sunrise_time_only, tzinfo=mst)
        sunset_dt_mst = dt.datetime.combine(forecast_date, sunset_time_only, tzinfo=mst)

        # Check if the forecast time is between sunrise and sunset on the same day
        if sunrise_dt_mst <= forecast_time_mst <= sunset_dt_mst:
            
            filtered_forecast.append({
                "datetime": forecast_time_mst,
                "date": forecast_time_mst.date().strftime('%Y-%m-%d'),
                "time": forecast_time_mst.strftime('%I:%M %p'),
                "temperature": hour["values"]["temperature"],
                "wind_speed": hour["values"]["windSpeed"],
                "precip_prob": hour["values"]["precipitationProbability"]
            })

    return filtered_forecast, sunset_time_only
    
def graph_forecast_w_highlight(filtered_forecast, sunset_dt_mst, select_date, date,
                               min_temp, max_wind, max_rain, 
                               temp_diff=0, wind_diff=0, rain_diff=0):

    today = dt.date.today()

    if select_date == today:
    
        # Define the timezone (e.g., US/Mountain)
        mst = timezone("US/Mountain")

        # Get the current time in MST (timezone-aware)
        now_utc = datetime.now(pytz.utc)

        # Format the current time to match the desired ISO 8601 format
        now_utc_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Check if the current time is later than the sunset time
        if now_utc_str > sunset_dt_mst:
            st.write("The current time is past sunset") 
            st.write("The :rainbow[Golf-able Oracle] is already dreaming about tomorrow's golf-abilities.")
            golfable_hrs_each_day(filtered_forecast, min_temp, max_wind, max_rain, select_date)
            return
    
    filtered_forecast_copy = filtered_forecast[0]

    # Convert to DataFrame
    df = pd.DataFrame(filtered_forecast_copy)
    
    # Step 2: Ensure 'datetime' is properly parsed and create combined 'datetime' column
    #df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce')
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['time'] = pd.to_datetime(df['time'], format='%I:%M %p', errors='coerce').dt.strftime('%I:%M %p')
    
    # Step 3: Add a combined datetime column (date + time)
    df['datetime_combined'] = df['date'].astype(str) + ' ' + df['time']
    df['datetime_combined'] = pd.to_datetime(df['datetime_combined'], errors='coerce')
    
    # Step 4: Melt the DataFrame to long format
    df_melted = df.melt(id_vars=['datetime_combined', 'date', 'time'], 
                        value_vars=['temperature', 'wind_speed', 'precip_prob'], 
                        var_name='Metric', value_name='Value')

    

    # Step 5: Pivot the data so each metric becomes a column
    pivot_df = df_melted.pivot(index='datetime_combined', columns='Metric', values='Value').reset_index()

    # Step 6: Sort data by combined datetime
    pivot_df = pivot_df.sort_values(by='datetime_combined')

    # Step 7: Extract 'time' for display (AM/PM format)
    pivot_df['time_display'] = pivot_df['datetime_combined'].dt.strftime('%I:%M %p')
    
    # Step 8: Filter by a specific date (e.g., '2024-11-19') before plotting
    selected_date = str(select_date)
    
    daily_df = pivot_df[pivot_df['datetime_combined'].dt.date.astype(str) == selected_date]

    # Step 5: Filter data where all conditions are met
    highlight_df = daily_df[
        (daily_df['temperature'] >= min_temp) & 
        (daily_df['wind_speed'] <= max_wind) & 
        (daily_df['precip_prob'] <= max_rain)
    ]

    # Step 6: Initialize variables to track start and end times
    highlight_ranges = []
    start_time = None

    # Step 7: Loop through each row to find continuous intervals
    for i in range(len(highlight_df)):
        current_time = highlight_df.iloc[i]['datetime_combined']

        if start_time is None:
            start_time = current_time

        # Check for next row and 1-hour gap
        if i + 1 < len(highlight_df):
            next_time = highlight_df.iloc[i + 1]['datetime_combined']
            hour_diff = (next_time - current_time).total_seconds() / 3600

            if hour_diff > 1 or current_time.date() != next_time.date():
                highlight_ranges.append((start_time, current_time))
                start_time = None
        else:
            highlight_ranges.append((start_time, current_time))

    # Convert highlight_ranges to a DataFrame if not empty
    if highlight_ranges:
        highlight_ranges_df = pd.DataFrame(highlight_ranges, columns=['start_time', 'end_time'])
        highlight_ranges_df['start_date'] = highlight_ranges_df['start_time'].dt.date
        highlight_ranges_df['start_hour'] = highlight_ranges_df['start_time'].dt.strftime('%I:%M %p')
        highlight_ranges_df['end_hour'] = highlight_ranges_df['end_time'].dt.strftime('%I:%M %p')
    else:
        highlight_ranges_df = pd.DataFrame(columns=['start_time', 'end_time', 'start_date', 'start_hour', 'end_hour'])

    # Step 8: Plot with Plotly Express
    fig = px.line(
        daily_df.melt(
            id_vars=['time_display'], 
            value_vars=['precip_prob', 'temperature', 'wind_speed'], 
            var_name='Metric', 
            value_name='Value'),
        x='time_display',
        y='Value',
        color='Metric',
        labels={
            'Value': 'Measurement',
            'Metric': 'Metric',
            'time_display': 'Time (MST)'
        },
        title='Weather Metrics Over Time',
        markers=True
    )

    # Step 9: Add shaded areas for each continuous time range, only if highlight_ranges_df is not empty
    if not highlight_ranges_df.empty:
        for _, row in highlight_ranges_df.iterrows():
            fig.add_shape(
                type='rect',
                x0=row['start_hour'],
                x1=row['end_hour'],
                y0=0,
                y1=1,
                xref='x',
                yref='paper',
                fillcolor='rgba(144, 238, 144, 0.3)',  # Light green with transparency
                line=dict(width=1),
            )

    # Step 10: Customize the layout
    fig.update_layout(
        xaxis_title='Time (MST)',
        yaxis_title='Value (°F, mph, %)',
        legend_title='Metrics',
        template='plotly_dark',
        hovermode='x unified',
    )

    # Display the chart in Streamlit
    st.plotly_chart(fig)

    # Oracle Prophecy
    if temp_diff < 0 or wind_diff > 0 or rain_diff > 0:
        st.subheader("")
        st.subheader(":red[The] :rainbow[Golf-able Oracle] :red[Has Prophesied Sub-Bar Golf Ranges]")
        st.subheader(f"{select_date}")
        st.subheader("")

        golfable_hrs_each_day(filtered_forecast, min_temp, max_wind, max_rain, select_date)
        

    else:
        # Convert the timedelta to total hours as a float
        total_hours = highlight_ranges_df['end_time'] - highlight_ranges_df['start_time']
        total_hours_in_float = total_hours.dt.total_seconds() / 3600  # Converts timedelta to hours

        # Round the values to whole numbers
        total_hours_rounded = total_hours_in_float.round()

        # Convert to a string representation
        total_hours_string = total_hours_rounded.astype(int).astype(str).to_string(index=False)

        st.subheader("")
        st.subheader(f":green[The] :rainbow[Golf-able Oracle] :green[Has Prophesied] :blue[{total_hours_string}Hr] :green[of Golf-ability]")
        st.subheader(f"{select_date}")
        st.subheader("")

        golfable_hrs_each_day(filtered_forecast, min_temp, max_wind, max_rain, select_date)


def golfable_hrs_each_day(filtered_forecast, min_temp, max_wind, max_rain, select_date):
    filtered_forecast_day_copy = filtered_forecast[0]

    # Convert to DataFrame
    df = pd.DataFrame(filtered_forecast_day_copy)
    
    # Ensure 'datetime' is properly parsed and create combined 'datetime' column
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['time'] = pd.to_datetime(df['time'], format='%I:%M %p', errors='coerce').dt.strftime('%I:%M %p')
    df['datetime_combined'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'], errors='coerce')

    # Filter rows meeting the weather criteria
    qualifying_df = df[
        (df['temperature'] >= min_temp) &
        (df['wind_speed'] <= max_wind) &
        (df['precip_prob'] <= max_rain)
    ]

    # Group by date for consecutive hour calculations
    qualifying_df['day'] = qualifying_df['datetime_combined'].dt.date
    grouped = qualifying_df.groupby('day')

    # Initialize dictionary to store total hours per day
    daily_hours = {day: 0 for day in df['date'].dt.date.unique()}  # Start with 0 for all days

    for day, group in grouped:
        group = group.sort_values(by='datetime_combined')
        total_consecutive_hours = 0
        current_start_time = None

        for i in range(len(group)):
            current_time = group.iloc[i]['datetime_combined']

            if current_start_time is None:
                current_start_time = current_time

            if i + 1 < len(group):
                next_time = group.iloc[i + 1]['datetime_combined']
                hour_diff = (next_time - current_time).total_seconds() / 3600

                if hour_diff > 1:
                    total_consecutive_hours += (current_time - current_start_time).total_seconds() / 3600
                    current_start_time = None
            else:
                total_consecutive_hours += (current_time - current_start_time).total_seconds() / 3600

        daily_hours[day] = round(total_consecutive_hours)

    # Convert total consecutive hours to a list
    total_consecutive_hours_list = list(daily_hours.values())

    week_day_metrics(select_date, total_consecutive_hours_list)


def week_day_metrics(select_date, total_consecutive_hours_list):

    # Get today's date
    today = dt.date.today()
    # Convert today to string
    today_to_string = str(today)
    # Convert the string to a datetime object
    today_date_obj = datetime.strptime(today_to_string, '%Y-%m-%d')

    # Convert select_date to string
    date_to_str = str(select_date)

    # Get the day of the week
    day_of_week_str = today_date_obj.strftime('%A')

    # Create a list of the next 5 days
    six_days_date_list = [(today_date_obj + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(0, 6)]
    
    # Create a list of the corresponding weekday labels
    six_days_name_list = [(today_date_obj + timedelta(days=i)).strftime('%A') for i in range(0, 6)]

    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1], gap='large')
    
    with col1:
        st.metric(
            label=six_days_date_list[0],
            value=six_days_name_list[0][:3],
            delta=-1 if total_consecutive_hours_list[0] == 0 else total_consecutive_hours_list[0]
        )
        date_str = six_days_date_list[0]
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        select_date = date_obj.date()
        day_3_button = st.button(f"🌤️ :blue[{six_days_name_list[0][:3]}] 📈",
                                on_click=on_button_click, 
                                args=(data, select_date),)
            
    with col2:
        st.metric(
            label=six_days_date_list[1],
            value=six_days_name_list[1][:3],
            delta=-1 if total_consecutive_hours_list[1] == 0 else total_consecutive_hours_list[1]
        )
        date_str = six_days_date_list[1]
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        select_date = date_obj.date()
        day_3_button = st.button(f"🌤️ :blue[{six_days_name_list[1][:3]}] 📈",
                                on_click=on_button_click, 
                                args=(data, select_date),)
        
    with col3:
        st.metric(
            label=six_days_date_list[2],
            value=six_days_name_list[2][:3],
            delta=-1 if total_consecutive_hours_list[2] == 0 else total_consecutive_hours_list[2]
        )
        date_str = six_days_date_list[2]
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        select_date = date_obj.date()
        day_4_button = st.button(f"🌤️ :blue[{six_days_name_list[2][:3]}] 📈",
                                on_click=on_button_click, 
                                args=(data, select_date),)

    with col4:
        st.metric(
            label=six_days_date_list[3],
            value=six_days_name_list[3][:3],
            delta=-1 if total_consecutive_hours_list[3] == 0 else total_consecutive_hours_list[3]
        )
        date_str = six_days_date_list[3]
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        select_date = date_obj.date()
        day_5_button = st.button(f"🌤️ :blue[{six_days_name_list[3][:3]}] 📈",
                                on_click=on_button_click, 
                                args=(data, select_date),)

    with col5:
        st.metric(
            label=six_days_date_list[4],
            value=six_days_name_list[4][:3],
            delta=-1 if total_consecutive_hours_list[4] == 0 else total_consecutive_hours_list[4]
        )
        date_str = six_days_date_list[4]
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        select_date = date_obj.date()
        day_6_button = st.button(f"🌤️ :blue[{six_days_name_list[4][:3]}] 📈",
                                    on_click=on_button_click, 
                                    args=(data, select_date),)

def on_button_click(data, select_date):
    get_data_for_select_date(data, select_date)
    

def display_golf_forecast(data, date, min_temp, max_wind, max_rain, sunrise_time, sunset_time, filtered_forecast):
    
    """Display golf forecast metrics and hourly weather data."""
    st.subheader(f"Golf-ability Weather Forecast Key Metrics") 
    st.subheader(f"{date}")
    st.write("")
    
    # Extract daily forecast for the specified date
    daily_forecast = next((item for item in data["data"]["timelines"][0]["intervals"] if item["startTime"].startswith(str(date))), None)
    
    if not daily_forecast:
        st.error(f"No forecast data available for {date}")
        return
    
    daily_high = daily_forecast["values"]["temperatureMax"]
    daily_max_wind = daily_forecast["values"]["windSpeed"]
    daily_max_precip = daily_forecast["values"]["precipitationProbability"]

    col1, col2, col3 = st.columns([1, 1, 1], gap='large')

    temp_diff = daily_high - min_temp
    wind_diff = daily_max_wind - max_wind
    rain_diff = daily_max_precip - max_rain

    # Temperature Metric
    with col1:
        if min_temp <= daily_high:
            temp_delta = f"Temp is {round(temp_diff)}°F above Min"
            temp_color = "normal"
        else:
            temp_delta = f"Temp is {round(temp_diff)}°F below {round(min_temp)}°F Min"
            temp_color = "normal"
        st.metric(
            label=temp_delta,
            value=f"High: {round(daily_high)}°F",
            delta=round(temp_diff),
            delta_color=temp_color
        )

    # Wind Speed Metric
    with col2:
        if max_wind > daily_max_wind:
            wind_delta = f"Wind is {round(-wind_diff)}Mph below {round(max_wind)}Mph Max"
            wind_color = "inverse"
        else:
            wind_delta = f"Wind is {round(-wind_diff)}Mph above {round(max_wind)}Mph Min"
            wind_color = "inverse"
        st.metric(
            label=wind_delta,
            value=f"Avg: {round(daily_max_wind)}Mph",
            delta=round(wind_diff),
            delta_color=wind_color
        )

    # Rain Probability Metric
    with col3:
        if max_rain > daily_max_precip:
            rain_delta = f"Rain is {round(-rain_diff)}% below {round(max_rain)}% Max"
            rain_color = "inverse"
        else:
            rain_delta = f"Rain is {round(-rain_diff)}% above {round(max_rain)}% Min"
            rain_color = "inverse"
        st.metric(
            label=rain_delta,
            value=f"Chance: {round(daily_max_precip)}%",
            delta=round(rain_diff),
            delta_color=rain_color
        )

    st.write("")
    st.write(f"### Hourly Forecast for {date} from Twilight to Dusk 🏌🏻‍♂️")
    st.write("")
    
    # Convert sunrise and sunset times to MST
    utc = pytz.utc
    mst = pytz.timezone('US/Mountain')

    sunrise_dt_utc = dt.datetime.fromisoformat(sunrise_time[:-1])
    sunset_dt_utc = dt.datetime.fromisoformat(sunset_time[:-1])
    sunrise_dt_mst = utc.localize(sunrise_dt_utc).astimezone(mst)
    sunset_dt_mst = utc.localize(sunset_dt_utc).astimezone(mst)

    # Display sunrise and sunset times in MST
    st.write(f"🌅 Twilight starts at: {sunrise_dt_mst.strftime('%I:%M %p')}")
    st.write(f"🌇 Dusk ends at: {sunset_dt_mst.strftime('%I:%M %p')}")

    # Plot filtered forecast
    graph_forecast_w_highlight(filtered_forecast, sunset_time, date, sunset_dt_mst, min_temp, max_wind, max_rain, 
                               temp_diff, wind_diff, rain_diff)
    

def get_data_for_select_date(data, select_date=None):
    # Use today's date if no date is provided
    select_date = select_date or dt.date.today()

    # Loop over each of the 5 days to display weather forecasts
    for interval in data["data"]["timelines"][0]["intervals"]:
        # Extract the date for the current forecast interval
        forecast_date = dt.datetime.fromisoformat(interval["startTime"][:-1]).date()
        
        # Check if the forecast date matches the selected date
        if forecast_date == select_date:
            # Fetch sunrise and sunset times from this specific interval
            sunrise_time = interval["values"]["sunriseTime"]
            sunset_time = interval["values"]["sunsetTime"]
            
            # Filter the forecast for the current date
            filtered_forecast = filter_forecast_by_sunrise_sunset(
                data["data"]["timelines"][1]["intervals"], sunrise_time, sunset_time)
            
            # Call the function to display the forecast
            display_golf_forecast(
                data, forecast_date, min_temp, max_wind, max_rain, sunrise_time, sunset_time, 
                filtered_forecast)

            return select_date

####### Initial Streamlit page configuration #######
    
st.set_page_config(
page_title = "Golf Weather Oracle",
page_icon = "Active",
layout = "wide",
)

# User inputs
st.sidebar.header(":green[City Location]")
city = st.sidebar.text_input("Example: Denver")

st.sidebar.header(":green[Min Golf-able Temp]")
min_temp = st.sidebar.number_input("°F", value=50, step=1)

st.sidebar.header(":green[Max Golf-able Wind Speed]")
max_wind = st.sidebar.number_input("Mph", value=15, step=1)

st.sidebar.header(":green[Max Golf-able Precipitation]")
max_rain = st.sidebar.number_input("%", value=20, step=1)

st.sidebar.header(":blue[Once the above values have been properly entered]")
st.sidebar.header(":blue[You may be permitted to]")

st.sidebar.write("")

golf_oracle_button = st.sidebar.button("⛳ :rainbow[Consult the Golf-able Oracle] 🧙‍♂️")
    
# CSS to center the elements
st.markdown(
    """
    <style>
    .center {
        display: flex;
        justify-content: center;
        text-align: center;
        color: rgba(255, 105, 180, 0.7)
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Initialize session state for content visibility 
if "content_visible" not in st.session_state: 
    st.session_state.content_visible = True

welcome_content1 = st.empty()
welcome_content2 = st.empty()
welcome_content3 = st.empty()
welcome_content4 = st.empty()
welcome_content5 = st.empty()
welcome_content6 = st.empty()

# Display initial content if content is visible 
if st.session_state.content_visible:
    # Centering the headers
    welcome_content1.markdown("<h1 class='center'>An EsteStyle Streamlit Page Where Python Wiz Meets Data Viz!</h1>", unsafe_allow_html=True)
    welcome_content2.markdown("<h1 class='center'></h1>", unsafe_allow_html=True)

    welcome_content3.markdown("<img src='https://1drv.ms/i/s!ArWyPNkF5S-foaAQmGTqlTr29Hp56w?embed=1&width=660' width='300' style='display: block; margin: 0 auto;'>" , unsafe_allow_html=True)

    welcome_content4.markdown("<h1 class='center'></h1>", unsafe_allow_html=True)

    welcome_content5.markdown("<h2 class='center'>Enter your city location & minimum golf-able weather conditions</h2>", unsafe_allow_html=True)
    welcome_content6.markdown("<h2 class='center'>Then press the Golf-able Oracle button for a consultation</h2>", unsafe_allow_html=True)

# Fetch and display weather data
if golf_oracle_button:
    st.session_state.content_visible = False
    welcome_content1.empty()
    welcome_content2.empty()
    welcome_content3.empty()
    welcome_content4.empty()
    welcome_content5.empty()
    welcome_content6.empty()
    
    data = get_weather_forecast(city)
    
    if data:
        # Loop over each of the 5 days to display weather forecasts
        # Call the function for today's date
        get_data_for_select_date(data)
