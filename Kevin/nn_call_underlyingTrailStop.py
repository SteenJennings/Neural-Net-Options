# In this algorithm, we are importing a list of 'buy' dates from a github csv.
# We will purchase call options on these dates and sell them with a trailing stop-limit.
# Resources - https://www.quantconnect.com/forum/discussion/9482/simple-example-long-put-hedge/p1?ref=towm
# Resources - https://www.quantconnect.com/tutorials/introduction-to-options/quantconnect-options-api#QuantConnect-Options-API-Algorithm

from clr import AddReference
AddReference("System")
AddReference("QuantConnect.Algorithm")
AddReference("QuantConnect.Common")

from System import *
from QuantConnect import *
from QuantConnect.Algorithm import *
from datetime import timedelta
import pandas as pd
import io
import requests
from QuantConnect.Data.Custom.CBOE import * # get pricing data

class BasicTemplateOptionsAlgorithm(QCAlgorithm):

    highestUnderlyingPrice = 0
    newStopPrice = 0
    
    def Initialize(self):
        # NOTE: QuantConnect provides equity options data from AlgoSeek going back as far as 2010.
        # The options data is available only in minute resolution, which means we need to consolidate
        # the data if we wish to work with other resolutions.
        self.SetStartDate(2018, 5, 3)
        self.SetEndDate(2018, 5, 24)
        self.SetCash(100000) # Starting Cash for our portfolio

        # Equity Info Here
        self.stockSymbol = "ROKU" # stock symbol here
        self.equity = self.AddEquity(self.stockSymbol, Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.option = self.AddOption(self.stockSymbol)
        self.option_symbol = self.option.Symbol
        # use the underlying equity as the benchmark
        #self.SetBenchmark(self.option_symbol)
        
        # Option Contracts
        self.contract = str()
        self.contractList = []
        self.buyOptions = 0 # buy signal
        self.DaysBeforeExp = 3 # close the options this many days before expiration
        self.OTM = 0.10 # target OTM %
        self.MinDTE = 15 # contract minimum DTE
        self.MaxDTE = 30 # contract maximum DTE
        self.contractAmounts = 1 # number of contracts to purchase
        self.portfolioRisk = 0.1 # percentage of portfolio to be used for purchases
        
        # Download NN Buy Signals from Github Raw CSV
        #self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/amd_predictions_05072021.csv"
        #self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/amzn_predictions_qc_052121.csv"
        #self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/GOOG_pred.csv"
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/ROKU_pred.csv"
        
        # modify dataframes add month/day/year, filter df to predictions only, drop date and 
        # prediction columns
        df = pd.read_csv(io.StringIO(self.Download(self.url)))
        df[['year','month','day']] = df['dates'].str.split("-", expand = True)
        df.columns = df.columns.str.lower()
        df = df[df['prediction'] == 1]
        df['year'] = df['year'].astype(int)
        df = df[df['year'] >= 2010]
        df = df.drop(columns=['dates','prediction'])
        buyArray = df.to_numpy()
        
        # Next step is to iterate through the predictions and schedule a buy event
        for x in buyArray:
            # Schedule Buys - https://www.quantconnect.com/docs/algorithm-reference/scheduled-events
            self.Schedule.On(self.DateRules.On(int(x[0]), int(x[1]), int(x[2])), \
                            self.TimeRules.At(9,35), \
                            self.BuySignal)
        '''
        self.Schedule.On(self.DateRules.On(2012, 3, 20), \
                            self.TimeRules.At(9,35), \
                            self.BuySignal)
        '''

    def OnData(self,slice):
        # OnData event is the primary entry point for your algorithm. Each new data point will be pumped in here.
        
        if self.Portfolio.Cash <= 10000:
            self.Log("Low Balance < $10,000")
        elif self.buyOptions == 1:
            self.BuyCall(slice)
        
        if self.contractList:
            for i in self.contractList:
                if(i.Symbol.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                    self.Liquidate(i.Symbol, "Closed: too close to expiration")
                    self.Log("Closed: too close to expiration")
                    self.contractList.remove(i)
                
                elif self.equity.Price > self.highestUnderlyingPrice:
                    self.highestUnderlyingPrice = self.equity.Price
                    self.newStopPrice = round((self.highestUnderlyingPrice * 0.95),2)
                    #self.Debug(str(self.stockSymbol)+ ": " + str(self.highestUnderlyingPrice) + " Stop: " + str(self.newStopPrice))
                    self.Log(str(self.stockSymbol)+ ": " + str(self.highestUnderlyingPrice) + " Stop: " + str(self.newStopPrice))
                
                elif self.equity.Price <= self.newStopPrice:
                    self.Liquidate(i.Symbol, "Stop Loss - Underlying Price" )
                    self.Log("Closed: Stop Loss - Underlying Price: " + str(self.equity.Price))
                    self.contractList.remove(i)
                    self.newStopPrice = 0
    
    def FilterOptions(self,slice):
        otmContractLimit = int(self.equity.Price * self.OTM)

        # set our strike/expiry filter for this option chain
        #self.option.SetFilter(0, otmContractLimit, timedelta(self.MinDTE), timedelta(self.MaxDTE))
        
        # By default, the option universe is filtered down to contracts that expire within 35 days, 
        # one contract below and another above ATM, and exclude weekly. A different set of contracts 
        # can be chosen with the SetFilter method:
        self.option.SetFilter(lambda universe: universe.WeeklysOnly().Strikes(0, otmContractLimit).Expiration(timedelta(self.MinDTE), timedelta(self.MaxDTE)))
    
    
    # Sets 'Buy' Indicator to 1
    def BuySignal(self):
        self.Log("BuySignal: Fired at : {0}".format(self.Time))
        self.buyOptions = 1

    # Buys a Call Option - 
    def BuyCall(self, slice):
        
        self.FilterOptions(slice)
        
        for i in slice.OptionChains:
            if i.Key != self.option_symbol: continue
            chain = i.Value

            # we sort the contracts to find OTM contract with farthest expiration
            contracts = sorted(sorted(sorted(chain, \
                key = lambda x: abs(chain.Underlying.Price - x.Strike)), \
                key = lambda x: x.Expiry, reverse=True), \
                key = lambda x: x.Right)
            
            if len(contracts) == 0: continue
            self.contract = contracts[0]

        # if found, trade it
        if self.contract:
            self.MarketOrder(self.contract.Symbol, self.contractAmounts)
            self.contractList.append(self.contract)
            self.contract = str()
            self.buyOptions = 0

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status != OrderStatus.Filled:
            return
        
        self.Log(str(orderEvent))