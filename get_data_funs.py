from dash import Dash, dcc, html, Input, Output, State, callback_context
from plotly.subplots import make_subplots
from whitenoise import WhiteNoise

import numpy as np
import pandas as pd
import urllib.request
import requests
import json
import io
import plotly.graph_objects as go
import plotly.express as px

from rq import Queue
from worker import conn

# data now comes from InfluxDB instead of ThingSpeak
from influx_data import get_OD_dataframe, get_temp_data

import logging
from scipy.signal import find_peaks
from scipy.optimize import curve_fit
from scipy.stats import linregress
from scipy import stats


def cull_data(dataframe):
    first_time_time = dataframe.index[0]
    last_time_time = dataframe.index[-1]
    # print("first time ", first_time_time)
    # print("last time ", last_time_time)

    df5 = dataframe.loc[(dataframe.index > (last_time_time - pd.Timedelta(2, 'h'))) & (dataframe.index < last_time_time)]

    df6 = dataframe.loc[(dataframe.index > first_time_time) & (dataframe.index < last_time_time - pd.Timedelta(2, 'h'))]
    df7 = df6.iloc[::10]

    selected_dataframe = pd.concat([df7, df5])
    return selected_dataframe

# Not being used
def format_OD_data(dataframe):
    """Returns a dataframe with the index set as the time (in datetime objects)

    Arguments:

    dataframe -- pandas dataframe directly from Thingspeak with 'created_at' column as strings formatted for time
    """
    df2 = dataframe.drop('entry_id', axis='columns')
    # convert time string to datetime, and switch from UTC to Eastern time
    df2['time'] = pd.to_datetime(df2['created_at']).dt.tz_convert('US/Eastern')
    df3 = df2.drop('created_at', axis='columns')
    df4 = df3.set_index('time')
    # print(df4.head())
    return df4


def rename_tubes(dataframe, newNames):
    """Modifies the input dataframe inplace to rename the columns to the newNames list
    List must be the same length and order as the columns you want to rename

    Arguments:

    dataframe -- pandas dataframe with the columns being the OD data of the tubes and the names of the columns being
    the name of each tube

    newNames -- list of names to rename the columns to. (must be in the order of how you want them renamed)
    """
    # rename tubes on update
    i = 0
    # print("rename df", dataframe)
    for col in dataframe.columns:
        dataframe.rename(columns={col: newNames[i]}, inplace=True)
        # print(newNames[i])
        i += 1

    return


def format_ln_data(dataframe, tube_num, offset_value=0):
    """Returns a pandas dataframe with columns OD and lnOD (log transformed data), index is the time values

    Arguments:

    dataframe -- pandas dataframe with time

    tube_num -- number (int) of which tube to get data on

    offset_value -- number for offset of OD data (default 0)
    """
    # print("ln dataframe", dataframe.head())
    # get the name of the tube
    tube_name = dataframe.columns[tube_num]

    # create new dataframe with tube_names and time index
    df2 = dataframe.loc[:, [tube_name]].dropna()
    # print(df2.head())

    # rename tube column to OD
    df2.rename({tube_name: 'OD'}, axis=1, inplace=True)
    
    # get rid of non-numeric values
    df3 = pd.to_numeric(df2.iloc[:,0], errors = 'coerce').to_frame('OD')
    df3 = df3.replace(np.inf, np.nan).dropna()
    
    df3['OD'] = df3['OD'] + offset_value
    # print("OD after blank val sub", df2['OD'])
    # calculate the natural log
    df3['lnOD'] = np.log(df3['OD'])
    # print(df2['lnOD'])
    print(df3[:5])
    
    return df3


