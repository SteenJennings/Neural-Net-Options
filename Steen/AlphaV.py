from alpha_vantage.timeseries import  TimeSeries
from alpha_vantage.techindicators import TechIndicators

API_key = '04ZKSL2N50GIBN85'

ts = TimeSeries(key = API_key, output_format='pandas')

#data = ts.get_daily('AMD')

#data[0]

ti = TechIndicators(key = API_key, output_format='pandas')
#data_rsi = ti.get_rsi('AMD', interval='daily',time_period=10, series_type='close')
data_ema = ti.get_ema('AMD',interval='daily',time_period=10, series_type='close')

data_ema[0]