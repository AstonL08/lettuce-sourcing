import streamlit as st
import pandas as pd
import plotly.express as px
import calendar

# ==========================================
# 1. ENGINEERING PARAMETERS
# ==========================================
PARAMS = {
    # Emissions Factors
    'ef_grid_mo': 800, 'ef_grid_az': 360, 'ef_grid_ca': 240,
    'ef_diesel': 10180, 'ef_plastic': 3.0,
    
    # Storage Energy (Refrigerated Warehouse)
    'energy_storage_daily': 0.008,  # kWh/kg/day
    
    # Truck Emissions (g CO2 per unit)
    'ef_truck_heavy': 186, 'ef_truck_med': 1298, 'ef_van': 400, 'ef_sedan': 250,
    
    # Vehicle MPG
    'mpg_truck_heavy': 6.5, 'mpg_truck_med': 9.0, 'mpg_van': 15.0, 'mpg_sedan': 30.0,
    
    # Payloads (lbs)
    'payload_heavy': 40000, 'payload_med': 15000, 'payload_van': 2000, 'payload_sedan': 200,
    
    # Growing CO2 (kg CO2e/kg)
    'grow_co2_yuma': 0.50, 'grow_co2_salinas': 0.42,
    'grow_co2_local_conv': 0.40, 'grow_co2_local_org': 0.20,
    'grow_energy_hydro': 16.67, # kWh/kg
    
    # Water (L/kg)
    'water_yuma': 250, 'water_salinas': 200, 'water_local': 100, 'water_hydro': 20,
    
    # Processing
    'proc_energy': 0.1, 'proc_plastic': 0.012,
    
    # Distances
    'dist_yuma': 1638, 'dist_salinas': 2040, 'dist_local': 33, 'dist_last_mile': 22,
    
    # Base Costs
    'price_base_nat_winter': 1.40, 'price_base_nat_summer': 1.70, 'price_base_nat_spike': 2.40,
    'price_base_local': 1.90, 'price_base_hydro': 3.50
}

# ==========================================
# 2. LOGIC FUNCTIONS
# ==========================================
def get_hydro_specs(vehicle_type):
    specs = {
        'Medium Truck': (PARAMS['ef_truck_med'], PARAMS['mpg_truck_med'], PARAMS['payload_med']),
        'Van': (PARAMS['ef_van'], PARAMS['mpg_van'], PARAMS['payload_van']),
        'Sedan': (PARAMS['ef_sedan'], PARAMS['mpg_sedan'], PARAMS['payload_sedan'])
    }
    return specs.get(vehicle_type, specs['Van'])

def calculate_supply_chain(month, inputs):
    results = []
    month_name = calendar.month_name[month]
    is_winter = (month < 4) or (month > 10)
    
    # --- 1. NATIONAL ---
    dist_nat = PARAMS['dist_yuma'] if is_winter else PARAMS['dist_salinas']
    ef_grid_nat = PARAMS['ef_grid_az'] if is_winter else PARAMS['ef_grid_ca']
    grow_co2_nat = PARAMS['grow_co2_yuma'] if is_winter else PARAMS['grow_co2_salinas']
    water_nat = PARAMS['water_yuma'] if is_winter else PARAMS['water_salinas']
    
    if month in [4, 11]: base_price_nat = PARAMS['price_base_nat_spike']
    elif is_winter: base_price_nat = PARAMS['price_base_nat_winter']
    else: base_price_nat = PARAMS['price_base_nat_summer']

    # Stage 1 & 2
    co2_proc_nat = (PARAMS['proc_energy'] * ef_grid_nat / 1000) + (PARAMS['proc_plastic'] * PARAMS['ef_plastic'])
    
    # Stage 3: Long Haul
    co2_trans_nat = (dist_nat * PARAMS['ef_truck_heavy']) / 907.185 / 1000
    cost_trans_nat = (dist_nat / PARAMS['mpg_truck_heavy'] * inputs['diesel_price']) / (PARAMS['payload_heavy'] * 0.4536)
    
    # Stage 4: Storage (DC) - 2.0 Days Dwell
    dwell_nat = 2.0
    co2_storage_nat = dwell_nat * PARAMS['energy_storage_daily'] * (inputs['mo_grid'] / 1000.0)

    # Stage 5: Last Mile (Mass Allocation)
    adjusted_payload_med = PARAMS['payload_med'] * (inputs['mass_allocation'] / 100.0)
    co2_lm_nat = (PARAMS['dist_last_mile'] * PARAMS['ef_truck_med']) / (adjusted_payload_med * 0.4536) / 1000
    cost_lm_nat = (PARAMS['dist_last_mile'] / PARAMS['mpg_truck_med'] * inputs['diesel_price']) / (adjusted_payload_med * 0.4536)
    
    results.append({'Chain': 'National', 'Stage': '1. Grow', 'CO2': grow_co2_nat, 'Month_Num': month, 'Month_Name': month_name})
    results.append({'Chain': 'National', 'Stage': '2. Process', 'CO2': co2_proc_nat, 'Month_Num': month, 'Month_Name': month_name})
    results.append({'Chain': 'National', 'Stage': '3. Transport', 'CO2': co2_trans_nat, 'Month_Num': month, 'Month_Name': month_name})
    results.append({'Chain': 'National', 'Stage': '4. Storage', 'CO2': co2_storage_nat, 'Month_Num': month, 'Month_Name': month_name})
    results.append({'Chain': 'National', 'Stage': '5. Last Mile', 'CO2': co2_lm_nat, 'Month_Num': month, 'Month_Name': month_name})

    summary_nat = {
        'Chain': 'National', 
        'Total_CO2': grow_co2_nat + co2_proc_nat + co2_trans_nat + co2_storage_nat + co2_lm_nat, 
        'Price': base_price_nat + cost_trans_nat + cost_lm_nat, 
        'Water': water_nat, 'Available': True
    }

    # --- 2. LOCAL ---
    is_local_season = month in [4, 5, 9, 10]
    if is_local_season:
        co2_grow_loc = PARAMS['grow_co2_local_org'] if inputs['local_type'] == 'Organic' else PARAMS['grow_co2_local_conv']
        co2_proc_loc = (PARAMS['proc_energy'] * inputs['mo_grid'] / 1000) + (PARAMS['proc_plastic'] * PARAMS['ef_plastic'])
        co2_trans_loc = (PARAMS['dist_local'] * PARAMS['ef_truck_heavy']) / 907.185 / 1000
        cost_trans_loc = (PARAMS['dist_local'] / PARAMS['mpg_truck_heavy'] * inputs['diesel_price']) / (PARAMS['payload_heavy'] * 0.4536)
        
        # Stage 4: Storage (DC) - 2.0 Days Dwell
        dwell_loc = 2.0
        co2_storage_loc = dwell_loc * PARAMS['energy_storage_daily'] * (inputs['mo_grid'] / 1000.0)
        
        results.append({'Chain': 'Local', 'Stage': '1. Grow', 'CO2': co2_grow_loc, 'Month_Num': month, 'Month_Name': month_name})
        results.append({'Chain': 'Local', 'Stage': '2. Process', 'CO2': co2_proc_loc, 'Month_Num': month, 'Month_Name': month_name})
        results.append({'Chain': 'Local', 'Stage': '3. Transport', 'CO2': co2_trans_loc, 'Month_Num': month, 'Month_Name': month_name})
        results.append({'Chain': 'Local', 'Stage': '4. Storage', 'CO2': co2_storage_loc, 'Month_Num': month, 'Month_Name': month_name})
        results.append({'Chain': 'Local', 'Stage': '5. Last Mile', 'CO2': co2_lm_nat, 'Month_Num': month, 'Month_Name': month_name})
        
        summary_loc = {
            'Chain': 'Local', 
            'Total_CO2': co2_grow_loc + co2_proc_loc + co2_trans_loc + co2_storage_loc + co2_lm_nat, 
            'Price': PARAMS['price_base_local'] + cost_trans_loc + cost_lm_nat, 
            'Water': PARAMS['water_local'], 'Available': True
        }
    else:
        # Create empty placeholders for off-season
        for stage in ['1. Grow', '2. Process', '3. Transport', '4. Storage', '5. Last Mile']:
            results.append({'Chain': 'Local', 'Stage': stage, 'CO2': 0.0, 'Month_Num': month, 'Month_Name': month_name})
        summary_loc = {'Chain': 'Local', 'Total_CO2': 0, 'Price': 0, 'Water': 0, 'Available': False}

    # --- 3. CEA (HYDRO) ---
    co2_grow_cea = (PARAMS['grow_energy_hydro'] * inputs['mo_grid']) / 1000
    co2_proc_cea = (PARAMS['proc_energy'] * inputs['mo_grid'] / 1000) + (PARAMS['proc_plastic'] * PARAMS['ef_plastic'])
    
    # Stage 4: Storage (DC) - 0.0 Days Dwell (Immediate Delivery)
    dwell_cea = 0.0
    co2_storage_cea = dwell_cea * PARAMS['energy_storage_daily'] * (inputs['mo_grid'] / 1000.0)

    ef_cea, mpg_cea, payload_cea = get_hydro_specs(inputs['cea_vehicle'])
    co2_lm_cea = (inputs['cea_dist'] * ef_cea) / (payload_cea * 0.4536) / 1000
    cost_lm_cea = (inputs['cea_dist'] / mpg_cea * inputs['diesel_price']) / (payload_cea * 0.4536)
    
    results.append({'Chain': 'CEA (Hydro)', 'Stage': '1. Grow', 'CO2': co2_grow_cea, 'Month_Num': month, 'Month_Name': month_name})
    results.append({'Chain': 'CEA (Hydro)', 'Stage': '2. Process', 'CO2': co2_proc_cea, 'Month_Num': month, 'Month_Name': month_name})
    results.append({'Chain': 'CEA (Hydro)', 'Stage': '3. Transport', 'CO2': 0, 'Month_Num': month, 'Month_Name': month_name})
    results.append({'Chain': 'CEA (Hydro)', 'Stage': '4. Storage', 'CO2': co2_storage_cea, 'Month_Num': month, 'Month_Name': month_name})
    results.append({'Chain': 'CEA (Hydro)', 'Stage': '5. Last Mile', 'CO2': co2_lm_cea, 'Month_Num': month, 'Month_Name': month_name})
    
    summary_cea = {
        'Chain': 'CEA (Hydro)', 
        'Total_CO2': co2_grow_cea + co2_proc_cea + co2_storage_cea + co2_lm_cea, 
        'Price': PARAMS['price_base_hydro'] + cost_lm_cea, 
        'Water': PARAMS['water_hydro'], 'Available': True
    }
    
    return results, [summary_nat, summary_loc, summary_cea]

# ==========================================
# 3. STREAMLIT APP UI
# ==========================================
st.set_page_config(page_title="Lettuce Supply Chain Optimizer", layout="wide")
st.title("🥗 Lettuce Sourcing Decision Support Tool")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Simulation Parameters")

month_names = list(calendar.month_name)[1:]
selected_month_name = st.sidebar.select_slider("Select Month (for Bubble Plot)", options=month_names, value="February")
selected_month = list(calendar.month_name).index(selected_month_name)

exclude_hydro_grow = st.sidebar.checkbox("Exclude Hydro Growing Stage?", value=False, help="Check this to hide the massive electricity carbon from Hydro.")

st.sidebar.markdown("---")
st.sidebar.subheader("Local Conditions")
input_mo_grid = st.sidebar.number_input("MO Grid Intensity (g CO2/kWh)", 0, 1200, 800)
input_diesel = st.sidebar.number_input("Diesel Price ($/gal)", 2.0, 7.0, 4.50)
input_mass_alloc = st.sidebar.slider("Truck Utilization % (Last Mile)", 10, 100, 100)

st.sidebar.markdown("---")
st.sidebar.subheader("Supply Chain Specifics")
input_local_type = st.sidebar.selectbox("Local Farm Type", ["Conventional", "Organic"])
input_cea_vehicle = st.sidebar.selectbox("CEA Delivery Vehicle", ["Van", "Medium Truck", "Sedan"])
input_cea_dist = st.sidebar.number_input("CEA Distance (Miles)", 0, 50, 7)

user_inputs = {
    'mo_grid': input_mo_grid,
    'diesel_price': input_diesel,
    'mass_allocation': input_mass_alloc,
    'local_type': input_local_type,
    'cea_vehicle': input_cea_vehicle,
    'cea_dist': input_cea_dist
}

# --- CALCULATION LOOP ---
all_month_breakdown = []
single_month_summary = []

for m in range(1, 13):
    breakdown, summaries = calculate_supply_chain(m, user_inputs)
    all_month_breakdown.extend(breakdown)
    if m == selected_month:
        single_month_summary = summaries

# Convert to DataFrame
df_breakdown = pd.DataFrame(all_month_breakdown)
df_summary = pd.DataFrame(single_month_summary)
df_summary = df_summary[df_summary['Available'] == True]

# CRITICAL FIX: Ensure CO2 is float to prevent "Count" histograms
df_breakdown['CO2'] = pd.to_numeric(df_breakdown['CO2'])
df_summary['Total_CO2'] = pd.to_numeric(df_summary['Total_CO2'])

# Zoom Logic
if exclude_hydro_grow:
    df_breakdown = df_breakdown[~((df_breakdown['Chain'] == 'CEA (Hydro)') & (df_breakdown['Stage'] == '1. Grow'))]
    hydro_grow_val = (PARAMS['grow_energy_hydro'] * input_mo_grid) / 1000
    df_summary.loc[df_summary['Chain'] == 'CEA (Hydro)', 'Total_CO2'] -= hydro_grow_val

# ==========================================
# 4. VISUALIZATION
# ==========================================

# --- CHART 1: BUBBLE PLOT ---
st.subheader(f"📊 Chart 1: Trade-off Analysis for {selected_month_name}")

# FIXED COLORS: National=Blue, Local=Green, Hydro=Purple
color_map = {
    'National': 'blue',
    'Local': 'green',
    'CEA (Hydro)': 'purple'
}

fig_bubble = px.scatter(
    df_summary, x="Total_CO2", y="Price", size="Water", color="Chain",
    hover_name="Chain", size_max=60, text="Chain",
    title=f"Cost ($) vs. Carbon (kg) - {selected_month_name}<br><sup>Size of bubble represents Water Usage (L)</sup>",
    labels={"Total_CO2": "Carbon Footprint (kg CO2e/kg)", "Price": "Est. Price ($/kg)"},
    template="plotly_white",
    color_discrete_map=color_map # <--- APPLIED HERE
)
fig_bubble.update_traces(textposition='top center')
fig_bubble.update_layout(height=500)
st.plotly_chart(fig_bubble, use_container_width=True)

# RAW DATA
with st.expander(f"View Raw Data for {selected_month_name}"):
    format_dict = {'Total_CO2': '{:.2f}', 'Price': '${:.2f}', 'Water': '{:.0f}'}
    st.dataframe(df_summary.style.format(format_dict, subset=['Total_CO2', 'Price', 'Water']))

# --- CHART 2: STACKED BAR (FACETED BY CHAIN) ---
# FIX: Sorting ensures Jan-Dec order and correct stacking
df_breakdown.sort_values(by=['Month_Num', 'Chain'], inplace=True)

st.subheader("📈 Chart 2: Annual Emissions Breakdown")

# We use FACET_COL="Chain" to create side-by-side panels.
fig_bar = px.bar(
    df_breakdown, 
    x="Month_Name", 
    y="CO2", 
    color="Stage", 
    facet_col="Chain", 
    title=f"Monthly Carbon Footprint by Supply Chain {'(Hydro Grow Excluded)' if exclude_hydro_grow else ''}",
    labels={"CO2": "kg CO2e per kg Lettuce", "Month_Name": ""},
    template="plotly_white",
    # Enforce order 1-5
    category_orders={
        "Month_Name": month_names, 
        "Stage": ["1. Grow", "2. Process", "3. Transport", "4. Storage", "5. Last Mile"]
    }
)

# Clean up axes labels
fig_bar.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
fig_bar.update_xaxes(tickangle=-45)

st.plotly_chart(fig_bar, use_container_width=True)