# -*- coding: utf-8 -*-
"""
Created on Thu Feb 20 13:32:32 2025

@author: Amritansh S
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import requests
#import numpy as np
from SmartApi import SmartConnect
import time
import sys
import pyotp
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
#import matplotlib.pyplot as plt
#import seaborn as sns
import plotly.express as px
import threading
import os 
from dotenv import load_dotenv



#########################################################################################
# Initialize SmartConnect
load_dotenv()
API_KEY = os.getenv('SMART_API_KEY')
obj = SmartConnect(api_key=API_KEY)
USER_NAME = os.getenv('USER_NAME')
PWD = os.getenv('PASSWORD')
totp = pyotp.TOTP(os.getenv('TOTP'))
toptp = totp.now()
data = obj.generateSession(USER_NAME, PWD, toptp)

refreshToken = data['data']['refreshToken']
feedToken = obj.getfeedToken()


userProfile = obj.getProfile(refreshToken)
print("logged in successfully")




# Cache LTP Data for 5 seconds to avoid multiple API calls
@st.cache_data(ttl=5)
def get_cached_ltp(exchange, tradingsymbol, token):
    return obj.ltpData(exchange, tradingsymbol, token)

# Cache Order Book for 10 seconds to prevent excessive calls
@st.cache_data(ttl=10)
def fetch_order_book():
    return obj.orderBook()


# Load the dataset
def load_data():
    file_path = r"67a4ae1b2090f585bfcd4fe9_1738845725.csv"
    df = pd.read_csv(file_path)
    df["Entry-Date"] = pd.to_datetime(df["Entry-Date"], errors='coerce')
    df["ExitDate"] = pd.to_datetime(df["ExitDate"], errors='coerce')
    return df


# Retry Session
def create_retry_session():
    global session
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    return session

session = create_retry_session()

# TELEGRAM
def telegram(message):
    bot_token = '1860332743:AAH2peiKmw_hQDQ2ICaWzAUbQ0RBHPlUHxk'
    bot_chatID = '1020359820'
    send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + bot_chatID + '&text=' + message
    try:
        requests.get(send_text)
    except Exception as e:
        print(f"Error sending Telegram message: {str(e)}")


# Get data from website in table format
def intializeSymbolTokenMap():
    url = 'https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json'
    d = session.get(url, timeout=10).json()  # Timeout added here
    global token_df
    token_df = pd.DataFrame.from_dict(d)
    token_df['expiry'] = pd.to_datetime(token_df['expiry'])
    token_df = token_df.astype({'strike': float})

intializeSymbolTokenMap()
print("importing tokens")

# Function to get token info for trading instruments
def getTokenInfo (df,exch_seg, instrumenttype,symbol,strike_price,pe_ce):
    strike_price = strike_price*100
    if exch_seg == 'NSE':
        eq_df = df[(df['exch_seg'] == 'NSE') & (df['symbol'].str.contains('EQ')) ]
        return eq_df[eq_df['name'] == symbol]
    elif exch_seg == 'NFO' and ((instrumenttype == 'FUTSTK') or (instrumenttype == 'FUTIDX')):
        return df[(df['exch_seg'] == 'NFO') & (df['instrumenttype'] == instrumenttype) & (df['name'] == symbol)].sort_values(by=['expiry'])
    elif exch_seg == 'NFO' and (instrumenttype == 'OPTSTK' or instrumenttype == 'OPTIDX'):
        return df[(df['exch_seg'] == 'NFO') & (df['instrumenttype'] == instrumenttype) & (df['name'] == symbol) & (df['strike'] == strike_price) & (df['symbol'].str.endswith(pe_ce))].sort_values(by=['expiry'])
    elif exch_seg == 'BFO' and (instrumenttype == 'OPTSTK' or instrumenttype == 'OPTIDX'):
        return df[(df['exch_seg'] == 'BFO') & (df['instrumenttype'] == instrumenttype) & (df['name'] == symbol) & (df['strike'] == strike_price) & (df['symbol'].str.endswith(pe_ce))].sort_values(by=['expiry'])


# Modify Order with Retry
def modify_order_with_retry(obj, orderparams):
    try:
        obj.modifyOrder(orderparams)
        print(f"Modified order: {orderparams['orderid']}")
    except Exception as e:
        print(f"Error modifying order: {str(e)}")
        telegram(f"Error modifying order: {str(e)}")

# Fetch Order Book with Retry
def get_order_book_with_retry(obj):
    try:
        return fetch_order_book()  # Cached Order Book
    except Exception as e:
        print(f"Error fetching order book: {str(e)}")
        telegram(f"Error fetching order book: {str(e)}")
        return None

# Function to place an order and handle rejection immediately
def place_order_with_check(obj, orderparams):
    try:
        response = obj.placeOrder(orderparams)  # Place the order
        print(f"Raw Response: {response}")  # Log the raw response

        # Handle response if it's a string (assume it's an order ID)
        if isinstance(response, str):
            print(f"Order placed successfully: {response}")
            telegram(f"Order placed successfully: {response}")
            return response  # Return the order ID

        # Handle response if it's a dictionary
        elif isinstance(response, dict):
            if response.get('status') == 'success':
                order_id = response['data']['orderid']
                print(f"Order placed successfully: {order_id}")
                telegram(f"Order placed successfully: {order_id}")
                return order_id
            else:
                error_message = response.get('message', 'Unknown error occurred')
                print(f"Order rejected: {error_message}")
                telegram(f"Order rejected: {error_message}")
                sys.exit()  # Exit the script if the order is rejected

        # Handle unexpected response format
        else:
            print(f"Unexpected response format: {response}")
            telegram(f"Unexpected response format: {response}")
            sys.exit()

    except Exception as e:
        print(f"Error placing order: {str(e)}")
        telegram(f"Error placing order: {str(e)}")
        sys.exit()  # Exit the script if an exception occurs

def place_stoploss_order_with_check(obj, orderparams):
    try:
        response = obj.placeOrder(orderparams)  # Place the stop-loss order
        print(f"Raw Response: {response}")  # Log the raw response

        # Handle response if it's a string (assume it's an order ID)
        if isinstance(response, str):
            print(f"Stop-loss order placed successfully: {response}")
            telegram(f"Stop-loss order placed successfully: {response}")
            return response  # Return the order ID

        # Handle response if it's a dictionary
        elif isinstance(response, dict):
            if response.get('status') == 'success':
                order_id = response['data']['orderid']
                print(f"Stop-loss order placed successfully: {order_id}")
                telegram(f"Stop-loss order placed successfully: {order_id}")
                return order_id
            else:
                error_message = response.get('message', 'Unknown error occurred')
                print(f"Stop-loss order rejected: {error_message}")
                telegram(f"Stop-loss order rejected: {error_message}")
                sys.exit()  # Exit the script if the stop-loss order is rejected

        # Handle unexpected response format
        else:
            print(f"Unexpected response format: {response}")
            telegram(f"Unexpected response format: {response}")
            sys.exit()

    except Exception as e:
        print(f"Error placing stop-loss order: {str(e)}")
        telegram(f"Error placing stop-loss order: {str(e)}")
        sys.exit()  # Exit the script if an exception occurs



sym='Sensex'

tok='99919000'


# Function to place an order
def place_order(quantity):
    #global ce_sl_orderid
    #global pe_sl_orderid
    global tokeninfpe
    global tokeninfce
    global ce_ltp
    global pe_ltp
    global ltp_spot
    
    ltpfinder=obj.ltpData('BSE',sym,tok)
    dataa=ltpfinder['data']
    print(ltpfinder)
    ltp_spot=(int(dataa['ltp']/100)*100)
    print(ltp_spot)


    print("found ltp spot price")




    #atm call and put
    i=0
    ce=ltp_spot-100

    pe=ltp_spot+100

    #getting tokeno and other info of the ce of that ltp one thing
    tokeninfce=getTokenInfo (token_df,'BFO','OPTIDX','SENSEX',ce,'CE').iloc[i]
    celtp_data=obj.ltpData('BFO',tokeninfce['symbol'],tokeninfce['token'])

    celtp=celtp_data['data']

    while True:
        global c
        try:
            print(i)
            tokeninfce=getTokenInfo (token_df,'BFO','OPTIDX','SENSEX',ce,'CE').iloc[i]
            celtp_data=obj.ltpData('BFO',tokeninfce['symbol'],tokeninfce['token'])

            celtp=celtp_data['data']

            ce_ltp=celtp['ltp']
            c=i
            break
        except:
            i+=1
            print(i)
            continue
            
            
    #getting ltp of the ce


    celtp_data=obj.ltpData('BFO',tokeninfce['symbol'],tokeninfce['token'])

    celtp=celtp_data['data']

    ce_ltp=celtp['ltp']
    print(ce_ltp)  

    print("atm call ltp found")

    tokeninfpe=getTokenInfo (token_df,'BFO','OPTIDX','SENSEX',pe,'PE').iloc[i]
    peltp_data=obj.ltpData('NFO',tokeninfpe['symbol'],tokeninfpe['token'])

    peltp=peltp_data['data']

    time.sleep(1)
    while True:
        global p
        try:
            print(i)
            tokeninfpe=getTokenInfo (token_df,'BFO','OPTIDX','SENSEX',pe,'PE').iloc[i]
            peltp_data=obj.ltpData('BFO',tokeninfpe['symbol'],tokeninfpe['token'])

            peltp=peltp_data['data']

            pe_ltp=peltp['ltp']
            p=i
            break
        except:
            i+=1
            print(i)
            continue


    #getting ltp of the pe


    peltp_data=obj.ltpData('BFO',tokeninfpe['symbol'],tokeninfpe['token'])

    peltp=peltp_data['data']

    pe_ltp=peltp['ltp']
        

    print("atm put ltp found")


    # finding strike ce

    while(ce_ltp>225):
        
        
        ce+=100
        time.sleep(0.3)
        #print(ce_ltp)
        #print(ce)
        
        tokeninfce=getTokenInfo (token_df,'BFO','OPTIDX','SENSEX',ce,'CE').iloc[c]
        
        celtp_data=obj.ltpData('BFO',tokeninfce['symbol'],tokeninfce['token'])
        celtp=celtp_data['data']
        ce_ltp=celtp['ltp']

        
        
        #getting ltp of the ce
        
        

    ce_sl=(ce_ltp/10)*2.5+ce_ltp
    ce_sl=round(ce_sl, 1)
    print(ce_ltp)
    telegram("ce found")


    print(datetime.now())    
    print("found call to short")


    # finding strike pe   

    while(pe_ltp>225):
        
        
        pe-=100
        time.sleep(0.3)
        #print(pe_ltp)
        #print(pe)
        
        tokeninfpe=getTokenInfo (token_df,'BFO','OPTIDX','SENSEX',pe,'PE').iloc[p]
        
        peltp_data=obj.ltpData('BFO',tokeninfpe['symbol'],tokeninfpe['token'])
        peltp=peltp_data['data']
        pe_ltp=peltp['ltp']

        
    print(tokeninfpe)
        #getting ltp of the ce
        
        
    pe_sl=(pe_ltp/10)*2.5+pe_ltp
    pe_sl=round(pe_sl, 1)
    print(pe_ltp)
    print("found put to short") 
    telegram("pe found")

    #placing order ce
    print(datetime.now())

    #  placing the CALL order
    orderparams_ce = {
        "variety": "NORMAL",
        "tradingsymbol": tokeninfce['symbol'],
        "symboltoken": tokeninfce['token'],
        "transactiontype": "SELL",
        "exchange": "BFO",
        "ordertype": "MARKET",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": "0",
        "squareoff": "0",
        "stoploss": "0",
        "quantity": str(quantity)
    }

    # Place CALL order and check for rejection
    ce_orderid = place_order_with_check(obj, orderparams_ce)
    

    # placing the PUT order
    orderparams_pe = {
        "variety": "NORMAL",
        "tradingsymbol": tokeninfpe['symbol'],
        "symboltoken": tokeninfpe['token'],
        "transactiontype": "SELL",
        "exchange": "BFO",
        "ordertype": "MARKET",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": "0",
        "squareoff": "0",
        "stoploss": "0",
        "quantity": str(quantity)
    }

    # Place PUT order and check for rejection
    pe_orderid = place_order_with_check(obj, orderparams_pe)

    print(f"CALL order placed: {ce_orderid}")
    print(f"PUT order placed: {pe_orderid}")
    telegram(f"CALL and PUT orders placed successfully. CE: {ce_orderid}, PE: {pe_orderid}")



    #  placing the STOP-LOSS order for CALL
    orderparams_ce_sl = {
        "variety": "STOPLOSS",
        "tradingsymbol": tokeninfce['symbol'],
        "symboltoken": tokeninfce['token'],
        "transactiontype": "BUY",
        "exchange": "BFO",
        "ordertype": "STOPLOSS_LIMIT",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": ce_sl + 30,  # Replace with calculated stop-loss price
        "squareoff": "0",
        "stoploss": "0",
        "quantity": str(quantity),  # Replace with your quantity
        "triggerprice": ce_sl  # Replace with calculated trigger price
    }

    # Place STOP-LOSS order for CALL and check for rejection
    #ce_sl_orderid = place_stoploss_order_with_check(obj, orderparams_ce_sl)
    st.session_state["ce_sl_orderid"] = place_stoploss_order_with_check(obj, orderparams_ce_sl)

    # Example of placing the STOP-LOSS order for PUT
    orderparams_pe_sl = {
        "variety": "STOPLOSS",
        "tradingsymbol": tokeninfpe['symbol'],
        "symboltoken": tokeninfpe['token'],
        "transactiontype": "BUY",
        "exchange": "BFO",
        "ordertype": "STOPLOSS_LIMIT",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": pe_sl + 30,  # Replace with calculated stop-loss price
        "squareoff": "0",
        "stoploss": "0",
        "quantity": str(quantity),  # Replace with your quantity
        "triggerprice": pe_sl  # Replace with calculated trigger price
    }

    # Place STOP-LOSS order for PUT and check for rejection
    #pe_sl_orderid = place_stoploss_order_with_check(obj, orderparams_pe_sl)
    st.session_state["pe_sl_orderid"] = place_stoploss_order_with_check(obj, orderparams_pe_sl)
    pe_sl_orderid = st.session_state.get("pe_sl_orderid")
    ce_sl_orderid = st.session_state.get("ce_sl_orderid")

    print(f"CALL stop-loss order placed: {ce_sl_orderid}")
    print(f"PUT stop-loss order placed: {pe_sl_orderid}")
    telegram(f"CALL and PUT stop-loss orders placed successfully. CE SL: {ce_sl_orderid}, PE SL: {pe_sl_orderid}")
    
    # Stop-Loss System
    print("Starting SL system")
    telegram("SL system started")

    global bkup_ce_ltp, bkup_pe_ltp
    # Initialize backup prices
    bkup_ce_ltp, bkup_pe_ltp = ce_ltp , pe_ltp
    
    
import queue



def monitor_stoploss():
    pe_sl_orderid = st.session_state.get("pe_sl_orderid")
    ce_sl_orderid = st.session_state.get("ce_sl_orderid")
    # Create a global queue to store alerts
    if "alert_queue" not in st.session_state:
        st.session_state["alert_queue"] = queue.Queue()
    while True:
        try:
            now = datetime.now()
            time.sleep(2)
            current_time = now.strftime("%H:%M:%S")
            #print(current_time)
            order_book = get_order_book_with_retry(obj)
            if not order_book:
                st.session_state["alert_queue"].put("⚠️ Order book fetch failed!")
                time.sleep(5)
                continue
            ltpfinder = obj.ltpData('BSE', sym, tok)
            dataa = ltpfinder['data']
            ltp_spot = (int(dataa['ltp'] / 100) * 100)
            
            # Update INDEX Spot Price
            ltpfinder = obj.ltpData('BSE', sym, tok)
            dataa = ltpfinder['data']
            ltp_spot = (int(dataa['ltp'] / 100) * 100)
            #index_placeholder.write(f"📊 **INDEX SPOT:** ₹{ltp_spot:.2f}")
            st.session_state["index_spot"] = ltp_spot
            
            # Update Live PnL
            current_pnl = get_live_pnl()
            
            #pnl_placeholder.write(f"💰 **Current PnL:** ₹{current_pnl:.2f}"
            st.session_state["pnl"] = current_pnl
            # Use Dictionary for Faster Lookup
            order_status = {order['orderid']: order['status'] for order in order_book['data']}
            if not order_book:
                print("Order book fetch failed, retrying...")
                time.sleep(5)
                continue

            for order in order_book['data']:
                if order['orderid'] == pe_sl_orderid:
                    sl_pe = order['status']
                elif order['orderid'] == ce_sl_orderid:
                    sl_ce = order['status']

            # Handling PE Stop-Loss Hit
            if order_status.get(pe_sl_orderid) == "complete":
                orderparams = {
                    "variety": "STOPLOSS",
                    "orderid": ce_sl_orderid,
                    "ordertype": "STOPLOSS_LIMIT",
                    "producttype": "INTRADAY",
                    "duration": "DAY",
                    "price": bkup_ce_ltp + 30,
                    "quantity": "20",
                    "tradingsymbol": tokeninfce['symbol'],
                    "symboltoken": tokeninfce['token'],
                    "exchange": "BFO",
                    "triggerprice": bkup_ce_ltp
                }
                modify_order_with_retry(obj, orderparams)
                print("PE SL hit")
                telegram("PE SL hit, CE SL adjusted")

                # Update Streamlit UI with error message
                #st.session_state["error_msg"] = "⚠️ PE Stop-Loss hit. Adjusting CE SL..."
                st.session_state["alert_queue"].put("🛑 PE Stop-Loss Hit! Adjusting CE SL...")
                break  # Exit the loop

            # Handling CE Stop-Loss Hit
            elif order_status.get(ce_sl_orderid) == "complete":
                orderparams = {
                    "variety": "STOPLOSS",
                    "orderid": pe_sl_orderid,
                    "ordertype": "STOPLOSS_LIMIT",
                    "producttype": "INTRADAY",
                    "duration": "DAY",
                    "price": bkup_pe_ltp + 30,
                    "quantity": "20",
                    "tradingsymbol": tokeninfpe['symbol'],
                    "symboltoken": tokeninfpe['token'],
                    "exchange": "BFO",
                    "triggerprice": bkup_pe_ltp
                }
                modify_order_with_retry(obj, orderparams)
                print("CE SL hit")
                telegram("CE SL hit, PE SL adjusted")

                # Update Streamlit UI with error message
                #st.session_state["error_msg"] = "⚠️ CE Stop-Loss hit. Adjusting PE SL..."
                st.session_state["alert_queue"].put("🛑 CE Stop-Loss Hit! Adjusting PE SL...")
                break  # Exit the loop

            # Exit at a specific time
            elif current_time > '15:43:50':
                telegram("Exit time reached, exiting...")

                # Update Streamlit UI
                #st.session_state["error_msg"] = "⏳ Exit time reached. Stopping trading..."
                st.session_state["alert_queue"].put("⏳ Exit time reached. Stopping trading...")
                break  # Exit the loop

            # Handling Order Rejections or Market Closure
            elif sl_ce in ["rejected", "cancelled"] or sl_pe in ["rejected", "cancelled"]:
                telegram("🚨 SOMETHING WRONG OR MARKET CLOSED")
                print("🚨 SOMETHING WRONG OR MARKET CLOSED")

                # Notify Streamlit UI
                #st.session_state["error_msg"] = "🚨 ERROR: Order Rejected or Market Closed."
                st.session_state["alert_queue"].put("🚨 ERROR: Order Rejected or Market Closed.")
                break  # Exit the loop

            else:
                time.sleep(3)  # Avoid excessive API calls
                #update_order_status()
                time.sleep(2)
                print("No SL hit, retrying...")

        except Exception as e:
            print(f"Unexpected error in SL loop: {str(e)}")
            telegram(f"Unexpected error in SL loop: {str(e)}")

            # Show error message on dashboard
            #st.session_state["error_msg"] = f"🚨 Unexpected error: {str(e)}"
            st.session_state["alert_queue"].put(f"🚨 Unexpected error: {str(e)}")
            break  # Exit the loop

    

   
    
#    return order_id

# Function to update order status randomly (for simulation)
def update_order_status():
    global df_orders
    # Simulated order book
    order_book_response = fetch_order_book()  # Cached Order Book

    # Extract the 'data' field from the response
    order_data = order_book_response.get('data', [])

    # Convert to Pandas DataFrame
    df_orders = pd.DataFrame(order_data)

    # Select relevant columns
    df_orders = df_orders[['orderid', 'tradingsymbol', 'transactiontype', 'quantity', 'price', 'status', 'updatetime']]




    
if "pnl_history" not in st.session_state:
    st.session_state["pnl_history"] = pd.DataFrame(columns=["Timestamp", "PnL"])

def get_live_pnl():
    try:
        order_book = fetch_order_book()
        if not order_book or 'data' not in order_book:
            return 0.0

        total_pnl = 0
        unique_symbols = {}

        for order in order_book['data']:
            if order['status'] == 'complete':
                symbol_key = (order['exchange'], order['tradingsymbol'], order['symboltoken'])
                unique_symbols[symbol_key] = None  # Placeholder for LTP

        for symbol_key in unique_symbols:
            try:
                ltp_data = get_cached_ltp(symbol_key[0], symbol_key[1], symbol_key[2])
                if ltp_data and 'data' in ltp_data:
                    unique_symbols[symbol_key] = float(ltp_data['data']['ltp'])
            except Exception as e:
                print(f"Error fetching LTP for {symbol_key}: {e}")

        for order in order_book['data']:
            if order['status'] == 'complete':
                buy_price = float(order['averageprice'])
                quantity = int(order['quantity'])
                symbol_key = (order['exchange'], order['tradingsymbol'], order['symboltoken'])

                current_price = unique_symbols.get(symbol_key)
                if current_price is not None:
                    total_pnl += (current_price - buy_price) * quantity if order['transactiontype'] == "BUY" else (buy_price - current_price) * quantity

        # Store PnL history
        timestamp = time.strftime("%H:%M:%S")
        new_data = pd.DataFrame([[timestamp, total_pnl]], columns=["Timestamp", "PnL"])
        st.session_state["pnl_history"] = pd.concat([st.session_state["pnl_history"], new_data]).tail(100)  # Keep only last 100 records

        return total_pnl
    except Exception as e:
        print(f"Error fetching PnL: {e}")
        return 0.0
    
    
# Function to fetch and display order book
  # Cache the order book for 10 seconds
def fetch_order_book_dashboard():
    order_book_response = get_order_book_with_retry(obj)

    if order_book_response and order_book_response['status']:
        order_data = order_book_response.get('data', [])
        df_orders = pd.DataFrame(order_data)

        # Select relevant columns
        if not df_orders.empty:
            df_orders = df_orders[['orderid', 'tradingsymbol', 'transactiontype', 'quantity', 'price', 'status', 'updatetime']]
            return df_orders
    return pd.DataFrame(columns=['orderid', 'tradingsymbol', 'transactiontype', 'quantity', 'price', 'status', 'updatetime'])

# Fetch order book data
df_orders = fetch_order_book_dashboard()



st.markdown(
    """
    <style>
        body {
            font-family: 'Arial', sans-serif;
        }
        .stMetric {
            font-size: 20px !important;
            color: #4CAF50;  /* Green color for emphasis */
        }
        .big-font {
            font-size: 22px !important;
            font-weight: bold;
        }
        .stButton>button {
            font-size: 18px !important;
            background-color: #007BFF !important;
            color: white !important;
            border-radius: 10px;
        }
    </style>
    """,
    unsafe_allow_html=True
)





# Create Tabs
tab1, tab2, tab3 = st.tabs(["📊 Live Trading", "📈 Performance Analysis", "📜 Holdings"])



from streamlit_autorefresh import st_autorefresh



# Run this function in a separate thread so Streamlit doesn’t slow down
#threading.Thread(target=update_dashboard, daemon=True).start()

with tab1:
    st.title("📈 Trading Dashboard")

    # Initialize session state for metrics if missing
    if "pnl" not in st.session_state:
        st.session_state["pnl"] = 0
    if "index_spot" not in st.session_state:
        st.session_state["index_spot"] = 0
    if "pnl_history" not in st.session_state:
        st.session_state["pnl_history"] = pd.DataFrame(columns=["Timestamp", "PnL"])

    # UI placeholders for dynamic updates
    pnl_placeholder = st.empty()
    index_placeholder = st.empty()

    # Function to update metrics
    def update_metrics():
        try:
            # Update PnL
            st.session_state["pnl"] = get_live_pnl()

            # Update Index Spot
            ltpfinder = get_cached_ltp('BSE', sym, tok)
            if ltpfinder and 'data' in ltpfinder:
                data = ltpfinder['data']
                st.session_state["index_spot"] = int(data['ltp'] / 100) * 100

        except Exception as e:
            st.error(f"Error updating metrics: {e}")

    # Run metric updates on each page refresh
    update_metrics()

    # Display updated metrics
    pnl_placeholder.metric("💰 Live PnL", f"₹{st.session_state.get('pnl', 0):.2f}")
    index_placeholder.metric("📊 Index Spot", f"₹{st.session_state.get('index_spot', 0):.2f}")
    
    
    # Display PnL Chart
    st.subheader("📈 Live Cumulative PnL Chart")
    if not st.session_state["pnl_history"].empty:
        fig = px.line(
            st.session_state["pnl_history"],
            x="Timestamp",
            y="PnL",
            title="Cumulative Profit/Loss Over Time",
            markers=True,
            line_shape="spline",
            color_discrete_sequence=["#EF553B"]
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ No PnL data yet. Tracking will start after the first update.")

    # Order Placement UI
    quantity = st.number_input("🔢 Enter Quantity", min_value=20, step=20)
    
    if st.button("✅ Execute Order"):
        st.session_state["trade_running"] = True  # Show loading message

        # Start order execution in a separate thread (Correct Syntax)
        threading.Thread(target=place_order, args=(quantity,), daemon=True).start()

        # Start stop-loss monitoring in a separate thread (Correct Syntax)
        threading.Thread(target=monitor_stoploss, daemon=True).start()





    # Order Book Display
    st.subheader("📜 Order Book")
    df_orders = fetch_order_book_dashboard()
    st.dataframe(df_orders, height=300, width=900)

    # Manual refresh button with debounce
    if st.button("🔄 Refresh Order Book"):
        time.sleep(1)
        update_order_status()
        
    # Streamlit UI Notification Section (Place this in the main UI)
    st.subheader("⚠️ System Alerts")

    # Display any error messages stored in session state
    if "error_msg" in st.session_state and st.session_state["error_msg"]:
        st.error(st.session_state["error_msg"])  # Display the error message
        st.stop()  # Stop further execution while keeping UI active

     # Display alerts from the queue (for errors from background threads)
    if "alert_queue" in st.session_state and not st.session_state["alert_queue"].empty():
        alert_message = st.session_state["alert_queue"].get()
        st.error(alert_message)  # Show the alert in the UI



    st.sidebar.subheader("❓ Help")
    st.sidebar.write("""
    - **Execute Order:** Place a new order with the specified quantity.
    - **Refresh Order Book:** Fetch the latest order book data.
    - **Live PnL:** View your current profit and loss.
    - **Historical Data:** Fetch and view historical market data.
    - **Price Alert:** Set alerts for specific price levels.
    """)

# **TAB 2: Trading Performance Analysis**
with tab2:
    st.title("📈 Trading Performance Dashboard")

    # Load Data
    df = load_data()

    # Sidebar Filters
    st.sidebar.header("Filters")
    selected_instrument = st.sidebar.multiselect(
        "Select Instrument", df["Instrument-Kind"].dropna().unique(),
        default=df["Instrument-Kind"].dropna().unique()
    )
    date_range = st.sidebar.date_input(
        "Select Date Range", [df["ExitDate"].min(), df["ExitDate"].max()]
    )

    # Filter Data
    df_filtered = df[
        (df["Instrument-Kind"].isin(selected_instrument)) & 
        (df["ExitDate"].between(pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])))
    ]

    # Display Key Metrics
    st.metric("Total Trades", len(df_filtered))
    st.metric("Total P/L", f"{df_filtered['P/L'].sum():,.2f}")
    st.metric("Win Rate", f"{(df_filtered['P/L'] > 0).mean() * 100:.2f}%")

    # **P/L Distribution (Interactive)**
    st.subheader("📊 P/L Distribution")
    fig = px.histogram(df_filtered, x="P/L", nbins=30, marginal="rug",
                       title="Profit/Loss Distribution",
                       color_discrete_sequence=["#636EFA"])
    fig.update_layout(bargap=0.2)
    st.plotly_chart(fig, use_container_width=True)

    # **Cumulative P/L Over Time (Interactive)**
    st.subheader("📈 Cumulative P/L Over Time")
    df_sorted = df_filtered.sort_values("ExitDate")
    df_sorted["Cumulative P/L"] = df_sorted["P/L"].cumsum()
    
    fig = px.line(df_sorted, x="ExitDate", y="Cumulative P/L",
                  title="Cumulative Profit/Loss Over Time",
                  markers=True, line_shape="spline",
                  color_discrete_sequence=["#EF553B"])
    st.plotly_chart(fig, use_container_width=True)

    # **Win/Loss Ratio (Interactive)**
    st.subheader("⚖️ Win/Loss Ratio")
    win_loss_counts = df_filtered["P/L"].apply(lambda x: "Win" if x > 0 else "Loss").value_counts()
    
    fig = px.pie(values=win_loss_counts, names=win_loss_counts.index,
                 title="Win/Loss Distribution",
                 color_discrete_sequence=["#00CC96", "#FF5733"])
    st.plotly_chart(fig, use_container_width=True)

    # **Strike Price vs. P/L (Interactive Scatter)**
    st.subheader("💹 Strike Price vs. P/L")
    # Fix: Ensure size values are positive
    fig = px.scatter(
        df_filtered, 
        x="StrikePrice", 
        y="P/L", 
        title="Strike Price vs. Profit/Loss",
        color="P/L",
        size=df_filtered["P/L"].abs(),  # Ensure size is always positive
        hover_data=["Instrument-Kind"],
        color_continuous_scale="Bluered"
    )
    st.plotly_chart(fig, use_container_width=True)


#  **TAB 3: Holdings**
with tab3:
    st.title("📜 Portfolio Holdings")

    def get_holdings():
        try:
            holdings = obj.holding()  # Fetch holdings using correct method
            if holdings["status"] == True:
                holdings_df = pd.DataFrame(holdings["data"])
                
                # Print available columns for debugging
                #st.write("Available Columns in Holdings Data:", holdings_df.columns.tolist())

                return holdings_df
            else:
                st.error("❌ Failed to fetch holdings.")
                return pd.DataFrame()
        except Exception as e:
            st.error(f"⚠️ Error fetching holdings: {str(e)}")
            return pd.DataFrame()

    holdings_df = get_holdings()

    if not holdings_df.empty:
        # Filter only existing columns
        required_columns = ['tradingsymbol', 'quantity', 'averageprice', 'ltp', 'pnl']
        available_columns = [col for col in required_columns if col in holdings_df.columns]

        st.subheader("📋 Holdings Overview")
        st.dataframe(holdings_df[available_columns])  # Show only available columns

        #  Ensure 'quantity' & 'averageprice' exist before calculation
        if "quantity" in holdings_df.columns and "averageprice" in holdings_df.columns:
            holdings_df["Total Invested"] = holdings_df["quantity"] * holdings_df["averageprice"]

            # Interactive Pie Chart for Investment Allocation
            st.subheader("📊 Investment Allocation")

            if not holdings_df["Total Invested"].isnull().all():
                fig = px.pie(
                    holdings_df,
                    names="tradingsymbol", 
                    values="Total Invested",
                    title="Stock Allocation by Investment",
                    hover_data={"Total Invested": ":,.2f"},  # ✅ Shows exact investment amount
                    labels={"tradingsymbol": "Stock", "Total Invested": "Investment (₹)"},
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig.update_traces(textinfo="percent+label", pull=[0.05] * len(holdings_df))  # ✅ Slight separation effect
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("⚠️ No valid investment data to display.")
        else:
            st.warning("⚠️ 'quantity' or 'averageprice' column missing, unable to calculate investment.")

    else:
        st.warning("⚠️ No holdings found!")
