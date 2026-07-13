import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from xgboost import XGBRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(page_title="Sales Forecasting Dashboard", layout="wide")
sns.set_style("whitegrid")
plt.rcParams['figure.dpi'] = 100

@st.cache_data
def load_data():
    df = pd.read_csv('train.csv')
    df['Order Date'] = pd.to_datetime(df['Order Date'], dayfirst=True)
    df['Ship Date'] = pd.to_datetime(df['Ship Date'], dayfirst=True)
    df['Year'] = df['Order Date'].dt.year
    df['Month'] = df['Order Date'].dt.month
    df['Quarter'] = df['Order Date'].dt.quarter
    df['Week'] = df['Order Date'].dt.isocalendar().week
    df['Season'] = df['Month'].apply(lambda m: 'Winter' if m in [12,1,2] else 'Spring' if m in [3,4,5] else 'Summer' if m in [6,7,8] else 'Autumn')
    return df

@st.cache_data
def get_monthly_data(df):
    return df.set_index('Order Date').resample('MS')['Sales'].sum().reset_index()

@st.cache_data
def get_weekly_data(df):
    return df.set_index('Order Date').resample('W-MON')['Sales'].sum().reset_index()

def build_and_forecast_xgboost(data_segment, periods=3):
    monthly = data_segment.set_index('Order Date').resample('MS')['Sales'].sum().reset_index()
    ml_df = monthly.copy()
    ml_df['Month'] = ml_df['Order Date'].dt.month
    ml_df['Quarter'] = ml_df['Order Date'].dt.quarter
    ml_df['Season'] = ml_df['Month'].apply(lambda m: 0 if m in [12,1,2] else 1 if m in [3,4,5] else 2 if m in [6,7,8] else 3)
    ml_df['Lag1'] = ml_df['Sales'].shift(1)
    ml_df['Lag2'] = ml_df['Sales'].shift(2)
    ml_df['Lag3'] = ml_df['Sales'].shift(3)
    ml_df['RollingMean3'] = ml_df['Sales'].shift(1).rolling(3).mean()
    ml_df = ml_df.dropna().reset_index(drop=True)
    
    features = ['Lag1', 'Lag2', 'Lag3', 'RollingMean3', 'Month', 'Quarter', 'Season']
    X = ml_df[features].values
    y = ml_df['Sales'].values
    
    model = XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42)
    model.fit(X, y)
    
    lags = ml_df['Sales'].iloc[-3:].tolist()
    preds = []
    for i in range(periods):
        lag1, lag2, lag3 = lags[-1], lags[-2], lags[-3] if len(lags) >= 3 else 0
        roll = np.mean(lags[-3:])
        month = (ml_df['Month'].iloc[-1] + i) % 12 + 1
        quarter = (month - 1) // 3
        season = 0 if month in [12,1,2] else 1 if month in [3,4,5] else 2 if month in [6,7,8] else 3
        X_pred = np.array([[lag1, lag2, lag3, roll, month, quarter, season]])
        pred = model.predict(X_pred)[0]
        preds.append(pred)
        lags.append(pred)
    
    return monthly, preds, model

df = load_data()
monthly = get_monthly_data(df)
weekly = get_weekly_data(df)

sidebar = st.sidebar
sidebar.title("📊 Navigation")
page = sidebar.radio("Select Page", ["📈 Sales Overview", "🔮 Forecast Explorer", "⚠️ Anomaly Report", "🎯 Demand Segments"])

if page == "📈 Sales Overview":
    st.title("Sales Overview")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Sales", f"${df['Sales'].sum():,.0f}")
    with col2:
        st.metric("Total Orders", f"{len(df):,}")
    with col3:
        st.metric("Avg Order Value", f"${df['Sales'].mean():,.2f}")
    
    st.subheader("Monthly Sales Trend")
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(monthly['Order Date'], monthly['Sales'], marker='o', color='#2563eb', linewidth=2)
    ax.set_title("Monthly Sales (2015-2018)", fontweight='bold')
    ax.set_xlabel("Date")
    ax.set_ylabel("Sales ($)")
    st.pyplot(fig, use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Sales by Category")
        cat_rev = df.groupby('Category')['Sales'].sum().sort_values(ascending=False)
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.barplot(x=cat_rev.index, y=cat_rev.values, palette='Blues_d', ax=ax)
        ax.set_title("Revenue by Category", fontweight='bold')
        ax.set_ylabel("Sales ($)")
        st.pyplot(fig, use_container_width=True)
    
    with col2:
        st.subheader("Sales by Region")
        reg_rev = df.groupby('Region')['Sales'].sum().sort_values(ascending=False)
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.barplot(x=reg_rev.index, y=reg_rev.values, palette='Greens_d', ax=ax)
        ax.set_title("Revenue by Region", fontweight='bold')
        ax.set_ylabel("Sales ($)")
        st.pyplot(fig, use_container_width=True)
    
    st.subheader("Seasonality Pattern")
    month_sales = df.groupby('Month')['Sales'].sum().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(12, 5))
    sns.barplot(x=month_sales.index, y=month_sales.values, palette='Oranges_d', ax=ax)
    ax.set_title("Total Sales by Calendar Month (All Years)", fontweight='bold')
    ax.set_xlabel("Month")
    ax.set_ylabel("Sales ($)")
    st.pyplot(fig, use_container_width=True)

elif page == "🔮 Forecast Explorer":
    st.title("Sales Forecast Explorer")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        segment_type = st.selectbox("Segment Type", ["Overall", "Category", "Region"])
    with col2:
        if segment_type == "Category":
            segment_name = st.selectbox("Select Category", df['Category'].unique())
            data_segment = df[df['Category'] == segment_name]
        elif segment_type == "Region":
            segment_name = st.selectbox("Select Region", df['Region'].unique())
            data_segment = df[df['Region'] == segment_name]
        else:
            segment_name = "All Data"
            data_segment = df
    with col3:
        forecast_periods = st.slider("Forecast Months", 1, 6, 3)
    
    monthly_segment, preds, model = build_and_forecast_xgboost(data_segment, forecast_periods)
    
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(monthly_segment['Order Date'], monthly_segment['Sales'], marker='o', label='Historical', color='#2563eb', linewidth=2)
    
    last_date = monthly_segment['Order Date'].iloc[-1]
    future_dates = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=forecast_periods, freq='MS')
    ax.plot(future_dates, preds, marker='o', linestyle='--', label='Forecast', color='#dc2626', linewidth=2)
    
    ax.fill_between(future_dates, np.array(preds) * 0.85, np.array(preds) * 1.15, alpha=0.2, color='#dc2626')
    ax.set_title(f"Sales Forecast — {segment_name}", fontweight='bold')
    ax.set_xlabel("Date")
    ax.set_ylabel("Sales ($)")
    ax.legend()
    st.pyplot(fig, use_container_width=True)
    
    forecast_df = pd.DataFrame({
        'Month': future_dates.strftime('%Y-%m'),
        'Forecast': [f"${p:,.0f}" for p in preds]
    })
    st.table(forecast_df)

elif page == "⚠️ Anomaly Report":
    st.title("Anomaly Detection")
    
    from sklearn.ensemble import IsolationForest
    
    weekly_an = weekly.copy()
    iso = IsolationForest(contamination=0.06, random_state=42)
    weekly_an['iso_flag'] = iso.fit_predict(weekly_an[['Sales']]) == -1
    
    roll_mean = weekly_an['Sales'].rolling(8, center=True, min_periods=1).mean()
    roll_std = weekly_an['Sales'].rolling(8, center=True, min_periods=1).std()
    weekly_an['zscore'] = (weekly_an['Sales'] - roll_mean) / roll_std
    weekly_an['z_flag'] = weekly_an['zscore'].abs() > 2
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Isolation Forest Anomalies", weekly_an['iso_flag'].sum())
    with col2:
        st.metric("Z-Score Anomalies", weekly_an['z_flag'].sum())
    with col3:
        st.metric("Flagged by Both", (weekly_an['iso_flag'] & weekly_an['z_flag']).sum())
    
    fig, axes = plt.subplots(2, 1, figsize=(12, 9))
    
    axes[0].plot(weekly_an['Order Date'], weekly_an['Sales'], color='#2563eb', label='Weekly Sales', linewidth=1.5)
    axes[0].scatter(weekly_an[weekly_an['iso_flag']]['Order Date'], weekly_an[weekly_an['iso_flag']]['Sales'],
                    color='#dc2626', s=80, marker='X', label='Anomaly', zorder=5)
    axes[0].set_title("Isolation Forest Detection", fontweight='bold')
    axes[0].legend()
    
    axes[1].plot(weekly_an['Order Date'], weekly_an['Sales'], color='#2563eb', label='Weekly Sales', linewidth=1.5)
    axes[1].scatter(weekly_an[weekly_an['z_flag']]['Order Date'], weekly_an[weekly_an['z_flag']]['Sales'],
                    color='#d97706', s=80, marker='D', label='Anomaly', zorder=5)
    axes[1].set_title("Z-Score Detection (>2σ)", fontweight='bold')
    axes[1].legend()
    
    plt.tight_layout()
    st.pyplot(fig, use_container_width=True)
    
    anomalies = weekly_an[weekly_an['iso_flag'] | weekly_an['z_flag']].sort_values('Sales', ascending=False)
    if len(anomalies) > 0:
        st.subheader("Top Anomalous Weeks")
        st.dataframe(anomalies[['Order Date', 'Sales', 'iso_flag', 'z_flag']].head(10), use_container_width=True)

elif page == "🎯 Demand Segments":
    st.title("Product Demand Segmentation")
    
    monthly_sc = df.groupby(['Sub-Category', pd.Grouper(key='Order Date', freq='MS')])['Sales'].sum().reset_index()
    feats = []
    for sc, g in monthly_sc.groupby('Sub-Category'):
        g = g.sort_values('Order Date')
        total_sales = g['Sales'].sum()
        volatility = g['Sales'].std()
        yearly = g.set_index('Order Date').resample('YS')['Sales'].sum()
        yoy = yearly.pct_change().dropna()
        growth_rate = yoy.mean() if len(yoy) > 0 else 0
        order_count = df[df['Sub-Category'] == sc].shape[0]
        avg_order_value = total_sales / order_count
        feats.append({'Sub-Category': sc, 'TotalSales': total_sales, 'GrowthRate': growth_rate,
                      'Volatility': volatility, 'AvgOrderValue': avg_order_value})
    feat_df = pd.DataFrame(feats).set_index('Sub-Category')
    
    X = feat_df.fillna(0)
    X_scaled = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=4, random_state=42, n_init=10)
    feat_df['Cluster'] = km.fit_predict(X_scaled)
    
    pca = PCA(n_components=2)
    coords = pca.fit_transform(X_scaled)
    feat_df['PC1'] = coords[:, 0]
    feat_df['PC2'] = coords[:, 1]
    
    cluster_labels = {
        0: 'High-Value, Volatile',
        1: 'Low Volume, Stable',
        2: 'High Volume, Stable',
        3: 'Growing Demand',
    }
    feat_df['ClusterLabel'] = feat_df['Cluster'].map(cluster_labels)
    
    fig, ax = plt.subplots(figsize=(10, 7))
    colors = ['#2563eb', '#16a34a', '#d97706', '#dc2626']
    for c in sorted(feat_df['Cluster'].unique()):
        sub = feat_df[feat_df['Cluster'] == c]
        ax.scatter(sub['PC1'], sub['PC2'], s=150, color=colors[c], label=cluster_labels[c], alpha=0.7)
        for idx, row in sub.iterrows():
            ax.annotate(idx, (row['PC1'], row['PC2']), fontsize=8, xytext=(5,5), textcoords='offset points')
    
    ax.set_title("Product Segments (PCA)", fontweight='bold')
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%})")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%})")
    ax.legend()
    ax.grid(alpha=0.3)
    st.pyplot(fig, use_container_width=True)
    
    st.subheader("Segment Profiles")
    segment_summary = feat_df[['TotalSales', 'GrowthRate', 'Volatility', 'AvgOrderValue', 'ClusterLabel']].copy()
    st.dataframe(segment_summary.sort_values('Cluster'), use_container_width=True)
