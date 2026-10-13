"""InfluxDB v2 replacements for get_OD_dataframe() and get_temp_data().

Drop-in compatible with the old ThingSpeak versions:
  * same function names and call signature (extra args are ignored)
  * returns a DataFrame indexed by US/Eastern datetimes named 'time'
  * OD frame always has 8 numeric columns 'field1'..'field8'
    (tubes with no data in Influx are left as NaN)
  * temp frame has 'Temp Int' and 'Temp Ext'

Expected Influx schema:
  bucket       : iodr_test  (override with INFLUX_BUCKET)
  _measurement : IODR_<n>   (n = device number, 1-3)
  _field       : OD
  tag          : tube_number  (1-8)

Connection settings come from iodr_secrets.py (or environment variables,
which take priority) so the token never ends up in this file.
"""
import os

import pandas as pd
from influxdb_client import InfluxDBClient

# ----------------------------------------------------------------------
# Connection (iodr_secrets.py, or environment variables)
# ----------------------------------------------------------------------
def _setting(name, default=""):
    """Environment variable first, then iodr_secrets.py, then the default."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import iodr_secrets
    except ImportError:
        return default
    return getattr(iodr_secrets, name, default)


INFLUX_URL = _setting("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = _setting("INFLUX_TOKEN")
INFLUX_ORG = _setting("INFLUX_ORG")
INFLUX_BUCKET = _setting("INFLUX_BUCKET", "iodr_test")

# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------
MEASUREMENT_PREFIX = "IODR_"     # device 1 -> measurement "IODR_1"
OD_FIELD = "OD"
TUBE_TAG = "tube_number"
N_TUBES = 8                      # the dashboard always shows 8 tubes

MAX_POINTS = 8000                # most recent points per tube
LOOKBACK = "-90d"                # how far back to look for those points

# If the tubes of one device are written with slightly different
# timestamps, rows in the table will be mostly empty. Setting this to e.g.
# "1m" snaps every tube onto a common 1-minute grid (last value per window).
# Leave as None if all tubes of a device share the same timestamp.
ALIGN_WINDOW = None

# Temperature: not configured yet. While this is None the temperature
# subplot is simply empty. Tell me how temperature is stored in Influx
# and this can be filled in.
TEMP_MEASUREMENT = None
# ----------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = InfluxDBClient(
            url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=60_000
        )
    return _client


def get_OD_dataframe(device, chIDs=None, readAPIkeys=None):
    """OD data for device 0-2: columns field1..field8, tz-aware time index."""
    measurement = f"{MEASUREMENT_PREFIX}{device + 1}"

    align = (
        f'  |> aggregateWindow(every: {ALIGN_WINDOW}, fn: last, createEmpty: false)\n'
        if ALIGN_WINDOW else ""
    )

    flux = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {LOOKBACK})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{OD_FIELD}")
{align}  |> tail(n: {MAX_POINTS})
  |> keep(columns: ["_time", "_value", "{TUBE_TAG}"])
  |> pivot(rowKey: ["_time"], columnKey: ["{TUBE_TAG}"], valueColumn: "_value")
  |> sort(columns: ["_time"])
'''
    result = _get_client().query_api().query_data_frame(flux)
    if isinstance(result, list):
        result = pd.concat(result, ignore_index=True) if result else pd.DataFrame()

    if result.empty:
        raise RuntimeError(
            f"No data returned from InfluxDB for measurement '{measurement}', "
            f"field '{OD_FIELD}' in bucket '{INFLUX_BUCKET}'."
        )

    df = result.copy()
    df["time"] = pd.to_datetime(df["_time"], utc=True).dt.tz_convert("US/Eastern")
    df = df.drop(columns=[c for c in df.columns if c in ("_time", "result", "table")])
    df = df.set_index("time").sort_index()

    # tag values arrive as the column names "1", "2", ...
    df.columns = [str(c) for c in df.columns]
    wanted = [str(i) for i in range(1, N_TUBES + 1)]
    df = df.reindex(columns=wanted)          # missing tubes -> all NaN
    df.columns = [f"field{i}" for i in range(1, N_TUBES + 1)]

    # flag bad data as NaN, like the ThingSpeak version did
    return df.apply(lambda col: pd.to_numeric(col, errors="coerce"))


def get_temp_data(device, chIDs=None, readAPIkeys=None):
    """Temperature for device 0-2: columns 'Temp Int' and 'Temp Ext'."""
    if TEMP_MEASUREMENT is None:
        # placeholder: empty (all-NaN) series so the rest of the app works
        idx = pd.date_range(end=pd.Timestamp.now(tz="US/Eastern"), periods=2, freq="h")
        idx.name = "time"
        return pd.DataFrame({"Temp Int": [float("nan")] * 2,
                             "Temp Ext": [float("nan")] * 2}, index=idx)
    raise NotImplementedError("Fill in the temperature query for your schema.")
