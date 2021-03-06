############################################################################################################################### 
#
# FileName: NN_Call_UnderlyingTrailStop.py
# Date: 5/25/2021
# Class: Capstone
# Description:  This code loads predictions from a CSV and schedules buy dates for each.  
#               The algorithm will purchase Call Options based on criteria such as % OTM, Min and Max DTE,
#               portfolio risk profile, etc.  After a contract is purchased, the algorithm closes (sells)  
#               the contract based on the risk criteria, which in this case is a combination of selling
#               X number of days before expiration or utilizing a tight trailing stop loss on the underlying
#               equity (whichever comes first).  
#
# Resources: Some code was taken from QuantConnect BootCamps, Documents, Tutorials and Forums. See Below:
#   https://www.quantconnect.com/forum/discussion/9482/simple-example-long-put-hedge/p1?ref=towm
#   https://www.quantconnect.com/tutorials/introduction-to-options/quantconnect-options-api#QuantConnect-Options-API-Algorithm
#   https://www.quantconnect.com/docs/algorithm-reference/handling-data
#   https://www.quantconnect.com/tutorials/applied-options/iron-condor
#   https://www.quantconnect.com/learning/course/1/boot-camp-101-us-equities
#   https://www.quantconnect.com/docs/algorithm-reference/scheduled-events
#
###############################################################################################################################
"""
from clr import AddReference
AddReference("System")
AddReference("QuantConnect.Algorithm")
AddReference("QuantConnect.Common")

from System import *
from QuantConnect import *
from QuantConnect.Algorithm import *
from QuantConnect.Data.Custom.CBOE import * # get pricing data specifically from CBOE
"""
from datetime import timedelta
import pandas as pd  # data processing
import io # converting data to csv 
import requests # importing data from URL

class BasicTemplateOptionsAlgorithm(QCAlgorithm):

    highestUnderlyingPrice = 0 # track underlying equity price
    newStopPrice = 0    # for moving stop loss
    
    def Initialize(self):
        # NOTE: QuantConnect provides equity options data from AlgoSeek going back as far as 2010.
        # The options data is available only in minute resolution, which means we need to consolidate
        # the data if we wish to work with other resolutions.
        
        # Download NN Buy Signals from Github Raw CSV
        #self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/SNAP_pred_2021-05-28%20(1).csv"
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/AMZN_pred_2021-05-27.csv"
        
        # modify dataframes
        df = pd.read_csv(io.StringIO(self.Download(self.url)))
        # split date column to three different columns for year, month and day 
        df[['year','month','day']] = df['date'].str.split("-", expand = True) 
        df.columns = df.columns.str.lower()
        df = df[df['prediction'] == 1]  # filter predictions
        df['year'] = df['year'].astype(int) 
        df['month'] = df['month'].astype(int) 
        df['day'] = df['day'].astype(int) 
        # filter predictions greater than 2010 because QuantConnect only provides
        # options data as far back as 2010
        df = df[df['year'] >= 2010]
        df = df.drop(columns=['date','prediction'])
        buyArray = df.to_numpy() # convert to array
        
        # Dates below are adjusted to match imported dates from NN
        self.SetStartDate(buyArray[0][1], buyArray[0][2], buyArray[0][3])
        self.SetEndDate(buyArray[-1][1], buyArray[-1][2], buyArray[-1][3])
        self.SetCash(100000) # Starting Cash for our portfolio

        # Equity Info Here
        self.stockSymbol = str(buyArray[0][0]) # stock symbol here
        self.equity = self.AddEquity(self.stockSymbol, Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.option = self.AddOption(self.stockSymbol, Resolution.Minute )
        self.option_symbol = self.option.Symbol
        self.SetBenchmark(self.stockSymbol)
        self.option.SetFilter(self.FilterOptions)
        
        # Option Contracts
        self.contract = str() # store option contract info
        self.contractList = [] # store purchased contracts
        self.buyOptionSignal = 0 # buy signal - loaded from csv
        self.DaysBeforeExp = 3 # close the options this many days before expiration
        self.stopLossPercent = .95 # underlying stop loss percentage
        self.OTM = 0.10 # target OTM %
        self.MinDTE = 25 # contract minimum DTE
        self.MaxDTE = 35 # contract maximum DTE
        self.buyNumOfContracts = 0 # number of contracts to purchase
        self.portfolioRisk = 0.05 # percentage of portfolio to be used for purchases
        self.AdjRiskForMomentum = 0 
        
        # iterate through the predictions and schedule a buy event
        self.daysInARow = 0
        for x in buyArray:
            
            self.Schedule.On(self.DateRules.On(x[1], x[2], x[3]), \
                            self.TimeRules.At(9,35), \
                            self.BuySignal)
        
        #self.Schedule.On(self.DateRules.On(2012, 3, 20), \
        #                    self.TimeRules.At(9,35), \
        #                    self.BuySignal)

    # OnData event is the primary entry point for your algorithm. 
    # Each new data point will be pumped in here.
    def OnData(self,slice):
        if self.Portfolio.Cash <= 10000:
            self.Log("Low Balance < $10,000")
            self.Debug("Low Balance < $10,000")
        elif self.buyOptionSignal == 1:
            self.BuyCall(slice)
            
        if self.contractList:
            
            # update stop loss if the underlying equity has increased
            if self.equity.Price > self.highestUnderlyingPrice:
                self.highestUnderlyingPrice = self.equity.Price
                self.newStopPrice = round((self.highestUnderlyingPrice * self.stopLossPercent),2)
                #self.Log(str(self.stockSymbol)+ ": " + str(self.highestUnderlyingPrice) \
                #            + " Stop: " + str(self.newStopPrice))
            
                
            # Sell all contracts if the underlying equity's price has dropped below the stop loss
            elif self.equity.Price <= self.newStopPrice:
                self.Liquidate()
                self.Log("Stop Loss Hit: Portfolio Liquidated")
                self.contractList = []
                self.highestUnderlyingPrice = 0
                self.newStopPrice = 0
                
            # check if the contracts are close to expiration
            for i in self.contractList:
                if(i.Symbol.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                    self.Liquidate(i.Symbol, "Closed: too close to expiration")
                    self.Log("Closed: too close to expiration")
                    self.contractList.remove(i)
    
    # Filter Options: https://www.quantconnect.com/docs/data-library/options
    def FilterOptions(self, universe):
        # Note: By default, the option universe is filtered down to contracts that expire within 35 days, 
        # one contract below and another above ATM, and exclude weekly. A different set of contracts 
        # can be chosen with the IncludeWeeklys() method
        
        otmContractLimit = int(self.equity.Price * self.OTM) # max OTM amount
        return universe.IncludeWeeklys().Strikes(0, \
                        otmContractLimit).Expiration(timedelta(self.MinDTE), timedelta(self.MaxDTE))
    
    # Sets 'Buy' Indicator to 1
    def BuySignal(self):
        self.Log("BuySignal: Fired at : {0}".format(self.Time))
        self.buyOptionSignal = 1

    # Buy a Call Option - 
    def BuyCall(self, slice):
        # save option contract chain, sort and filter
        for i in slice.OptionChains:
            if i.Key != self.option_symbol: continue
            chain = i.Value

            # we sort the contracts to find OTM contract with farthest expiration
            contracts = sorted(sorted(sorted(chain, \
                key = lambda x: abs(chain.Underlying.Price - x.Strike), reverse=True), \
                key = lambda x: x.Expiry, reverse=True), \
                key = lambda x: x.Right)
            
            if len(contracts) == 0: continue
            
            if contracts[0].AskPrice == 0: 
                self.contract = contracts[1]
            else: 
                self.contract = contracts[0]
        
        #self.Debug("Testing Stop Point")
        # submit an order to purchase a call
        if self.contract:
            self.buyNumOfContracts = int((self.portfolioRisk * self.Portfolio.Cash) / (self.contract.AskPrice * 100))
            if self.buyNumOfContracts < 1:
                self.buyNumOfContracts = 1
            self.MarketOrder(self.contract.Symbol, self.buyNumOfContracts)
            self.contractList.append(self.contract) # add contract to list
            self.contract = str()
            self.buyOptionSignal = 0 # reset buy signal
            #self.Log("Call Purchase: Underlying Price is " + str(self.equity.Price))
            #self.Debug("Call Purchase: Underlying Price is " + str(self.equity.Price))

    # Log Order Events
    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status != OrderStatus.Filled:
            return
        
        self.Log(str(orderEvent))