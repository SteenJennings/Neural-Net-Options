############################################################################################################################### 
#
# FileName: NN_Call_UnderlyingTrailStop.py
# Date: 5/25/2021
# Class: Capstone
# Description: This code loads buy signals from a CSV and schedules buy dates for each signal/prediction.  
#               The algorithm will purchase Call Options based on criteria such as % OTM, Min and Max DTE,
#               portfolio risk profile, etc.  After a contract is purchased, the algorithm closes (sells)  
#               the contract based on the risk profolio, which in this case is a combination of selling
#               X number of days before expiration or utilizing a tight trailing stop loss on the underlying
#               equity (whichever comes first).  
#
# Resources:
#   https://www.quantconnect.com/forum/discussion/9482/simple-example-long-put-hedge/p1?ref=towm
#   https://www.quantconnect.com/tutorials/introduction-to-options/quantconnect-options-api#QuantConnect-Options-API-Algorithm
#
###############################################################################################################################

from clr import AddReference
AddReference("System")
AddReference("QuantConnect.Algorithm")
AddReference("QuantConnect.Common")

from System import *
from QuantConnect import *
from QuantConnect.Algorithm import *
from datetime import timedelta
import pandas as pd  # for data processing
import io
import requests
from QuantConnect.Data.Custom.CBOE import * # get pricing data specifically from CBOE

class BasicTemplateOptionsAlgorithm(QCAlgorithm):

    highestUnderlyingPrice = 0 # track underlying equity price
    newStopPrice = 0    # for moving stop loss
    
    def Initialize(self):
        # NOTE: QuantConnect provides equity options data from AlgoSeek going back as far as 2010.
        # The options data is available only in minute resolution, which means we need to consolidate
        # the data if we wish to work with other resolutions.
        
        # Dates below are adjusted to match imported dates from NN
        self.SetStartDate(2021, 1, 1)
        self.SetEndDate(2021, 5, 26)
        self.SetCash(100000) # Starting Cash for our portfolio

        # Equity Info Here
        self.stockSymbol = "NVDA" # stock symbol here
        self.equity = self.AddEquity(self.stockSymbol, Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.option = self.AddOption(self.stockSymbol)
        self.option_symbol = self.option.Symbol
        
        # Option Contracts
        self.contract = str() # store option contract info
        self.contractList = [] # store purchased contracts
        self.buyOptions = 0 # buy signal - loaded from csv
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
        #self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/ROKU_pred.csv"
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/NVDA_pred_2021-05-27.csv"
        
        # modify dataframes
        df = pd.read_csv(io.StringIO(self.Download(self.url)))
        # split date column to three different columns for year, month and day 
        df[['year','month','day']] = df['date'].str.split("-", expand = True) 
        df.columns = df.columns.str.lower()
        df = df[df['prediction'] == 1]  # filter predictions
        df['year'] = df['year'].astype(int) 
        # filter predictions gereater than 2010 because QuantConnect only provides
        # options data as far back as 2010
        df = df[df['year'] >= 2010]
        df = df.drop(columns=['date','prediction'])
        buyArray = df.to_numpy() # convert to array
        
        # iterate through the predictions and schedule a buy event
        for x in buyArray:
            # Schedule Buys:
            #   https://www.quantconnect.com/docs/algorithm-reference/scheduled-events
            self.Schedule.On(self.DateRules.On(int(x[0]), int(x[1]), int(x[2])), \
                            self.TimeRules.At(9,35), \
                            self.BuySignal)
        '''
        self.Schedule.On(self.DateRules.On(2012, 3, 20), \
                            self.TimeRules.At(9,35), \
                            self.BuySignal)
        '''

    # OnData event is the primary entry point for your algorithm. 
    # Each new data point will be pumped in here.
    def OnData(self,slice):
        if self.Portfolio.Cash <= 10000:
            self.Log("Low Balance < $10,000")
        elif self.buyOptions == 1:
            self.BuyCall(slice)
        
        if self.contractList:
            
            # update stop loss if the underlying equity has increased
            if self.equity.Price > self.highestUnderlyingPrice:
                self.highestUnderlyingPrice = self.equity.Price
                self.newStopPrice = round((self.highestUnderlyingPrice * 0.95),2)
                self.Log(str(self.stockSymbol)+ ": " + str(self.highestUnderlyingPrice) \
                            + " Stop: " + str(self.newStopPrice))
            
            # Sell all contracts if the underlying equity's price has dropped below the stop loss
            elif self.equity.Price <= self.newStopPrice:
                for i in self.contractList:
                    self.Liquidate(i.Symbol, "Stop Loss - Underlying Price" )
                    self.Log("Closed: Stop Loss - Underlying Price: " + str(self.equity.Price))
                    self.contractList.remove(i)
                
                self.newStopPrice = 0
            
            # check if the contracts are too close to expiration
            if self.contractList:
                for i in self.contractList:
                    if(i.Symbol.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                        self.Liquidate(i.Symbol, "Closed: too close to expiration")
                        self.Log("Closed: too close to expiration")
                        self.contractList.remove(i)

    # Filter Options: https://www.quantconnect.com/docs/data-library/options
    def FilterOptions(self,slice):
        otmContractLimit = int(self.equity.Price * self.OTM) # max OTM amount

        # set our strike/expiry filter for this option chain
        #self.option.SetFilter(0, otmContractLimit, timedelta(self.MinDTE), timedelta(self.MaxDTE))
        
        # By default, the option universe is filtered down to contracts that expire within 35 days, 
        # one contract below and another above ATM, and exclude weekly. A different set of contracts 
        # can be chosen with the SetFilter method:
        self.option.SetFilter(lambda universe: universe.WeeklysOnly().Strikes(0, \
                        otmContractLimit).Expiration(timedelta(self.MinDTE), timedelta(self.MaxDTE)))
    
    
    # Sets 'Buy' Indicator to 1
    def BuySignal(self):
        self.Log("BuySignal: Fired at : {0}".format(self.Time))
        self.buyOptions = 1

    # Buy a Call Option - 
    def BuyCall(self, slice):
        self.FilterOptions(slice)
        
        # save option contract chain, sort and filter
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

        # submit an order to purchase a call
        if self.contract:
            self.MarketOrder(self.contract.Symbol, self.contractAmounts)
            self.contractList.append(self.contract) # add contract to list
            self.contract = str()
            self.buyOptions = 0 # reset buy signal

    # Log Order Events
    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status != OrderStatus.Filled:
            return
        
        self.Log(str(orderEvent))