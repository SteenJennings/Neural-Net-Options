# In this algorithm, we are importing a list of 'buy' dates from a github csv.
# We will purchase call options on these dates and sell them with a simple
# trailing stop-limit.
from io import StringIO
import pandas as pd
from datetime import timedelta
from QuantConnect.Data.Custom.CBOE import * # get pricing data

class BigCoolOrangutang(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2020, 11, 18)  # Set Start Date
        self.SetEndDate(2021, 5, 18) # Set End Date
        self.SetCash(100000)  # Set Strategy Cash
        
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/amd_predictions_05072021.csv"
        csv = self.Download(self.url)
        
        self.equity = self.AddEquity("AMD", Resolution.Daily)
        self.Securities["AMD"].SetDataNormalizationMode(DataNormalizationMode.Raw)
        
        todaysDate = self.Time - timedelta(days = 7)
        
        # Schedule Buy Calls after Market Open - At 9:31
        self.Schedule.On(self.DateRules.On(2020, 12, 1),self.TimeRules.At(9,31), self.BuyContracts)
        

    def OnData(self, data):
        if self.Portfolio.Invested: 
            return
        
        if not data.ContainsKey(self.equity.Symbol):
            return
        
        contracts = self.OptionChainProvider.GetOptionContractList(self.equity.Symbol, data.Time)
        self.underlyingPrice = self.Securities[self.equity.Symbol].Price
        over = self.underlyingPrice + 0.1 * self.underlyingPrice
        
        otm_calls = [i for i in contracts if i.ID.OptionRight == OptionRight.Call and 
                                            i.ID.StrikePrice >= over and 
                                            28 < (i.ID.Date - data.Time).days > 35]
                                            
        if len(otm_calls) == 0: return
        
        contract = sorted(sorted(otm_calls, key = lambda x: x.ID.Date), key = lambda x: x.ID.StrikePrice)[0]
        self.AddOptionContract(contract, Resolution.Minute)
        self.MarketOrder(contract,1)
        
    def BuyContracts(self):
        pass
    
    def SellContracts(self):
        pass