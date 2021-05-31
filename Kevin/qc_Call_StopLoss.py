############################################################################################################################### 
#
# FileName: qc_Call_StopLoss.py
# Date: 5/25/2021
# Class: Capstone
# Description:  This code loads predictions from a CSV and schedules buy dates for each.  
#               The algorithm will purchase Call Options based on criteria such as % OTM, Min and Max DTE,
#               portfolio risk profile, etc.  After a contract is purchased, the algorithm closes (sells)  
#               the contract based on the risk criteria, which in this case is a combination of selling
#               X number of days before expiration or utilizing a tight trailing stop loss on the contract AskPrice.  
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
    
    contractDictionary = {} # KVP to be used for trailing stop loss - track AskPrice highs
    contractList = []
    askPriceHigh = 0 # track underlying equity price
    
    def Initialize(self):
        # Download NN Buy Signals from Github Raw CSV
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/Final_NN_Output/DIS_pred_2021-05-30.csv"
        
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
        df = df.drop(columns=['date','prediction','expected','equal','correctbuysignal'])
        buyArray = df.to_numpy() # convert to array
        
        # NOTE: QuantConnect provides equity options data from AlgoSeek going back as far as 2010.
        # The options data is available only in minute resolution, which means we need to consolidate
        # the data if we wish to work with other resolutions.
        self.SetStartDate(buyArray[0][1], buyArray[0][2], buyArray[0][3])
        self.SetEndDate(buyArray[-1][1], buyArray[-1][2], buyArray[-1][3])
        self.SetCash(100000) # Starting Cash for our portfolio

        # Equity Info Here
        self.stockSymbol = str(buyArray[0][0]) # stock symbol here
        self.equity = self.AddEquity(self.stockSymbol, Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.option = self.AddOption(self.stockSymbol, Resolution.Minute )
        self.option_symbol = self.option.Symbol
        # use the underlying equity as the benchmark
        self.SetBenchmark(self.stockSymbol)
        
        # Option Contracts
        self.contract = str()
        self.buyOptions = 0 # buy signal
        self.DaysBeforeExp = 3 # close the options this many days before expiration
        self.OTM = 0.10 # target contract OTM %
        self.MinDTE = 25 # contract minimum DTE
        self.MaxDTE = 35 # contract maximum DTE
        self.contractAmounts = 1 # number of contracts to purchase
        self.portfolioRisk = 0.05 # percentage of portfolio to be used for purchases
        self.stopLossPercentage = .025 
        
        # Next step is to iterate through the predictions and schedule a buy event
        for x in buyArray:
            # Schedule Buys - https://www.quantconnect.com/docs/algorithm-reference/scheduled-events
            self.Schedule.On(self.DateRules.On(x[1], x[2], x[3]), \
                            self.TimeRules.At(9,31), \
                            self.BuySignal)
                            
        self.Schedule.On(self.DateRules.EveryDay(self.option_symbol), \
                 self.TimeRules.BeforeMarketClose(self.option_symbol, 5), \
                 self.EveryDayBeforeMarketClose)

    def OnData(self,slice):
        # OnData event is the primary entry point for your algorithm. Each new data point will be pumped in here.
        otmContractLimit = int(self.equity.Price * self.OTM)

        # set our strike/expiry filter for this option chain
        self.option.SetFilter(0, otmContractLimit, timedelta(self.MinDTE), timedelta(self.MaxDTE))
        
        if self.Portfolio.Cash > 10000 and self.buyOptions == 1:
            self.BuyCall(slice)

    def EveryDayBeforeMarketClose(self):
        if self.contractList:
            for i in self.contractList:
                if(i.Symbol.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                    self.Liquidate(i.Symbol, "Liquidate: Close to Expiration")
                    self.Log("Closed: too close to expiration")
                    self.contractList.remove(i)
                    #del self.contractDictionary[i]
                
                elif self.Securities[i.Symbol].AskPrice > self.contractDictionary[i]:
                    self.Log("Contract AskPrice is higher")
                    # Save the new high to highestContractPrice; then update the stop price 
                    self.contractDictionary[i] = self.Securities[i.Symbol].AskPrice
                    self.Log(self.stockSymbol + "- NewHigh: " + str(self.contractDictionary[i]) + \
                               " Stop: " + str(round((self.contractDictionary[i] * (1-self.stopLossPercentage)),2)))
                elif self.Securities[i.Symbol].AskPrice <= round((self.contractDictionary[i] * (1-self.stopLossPercentage)),2):
                    self.Liquidate(i.Symbol, "Liquidate: Stop Loss")
                    self.Log("Stop Loss Hit")
                    #del self.contractDictionary[i]
                    self.contractList.remove(i)
            else:
                return

    # Sets 'Buy' Indicator to 1
    def BuySignal(self):
        self.Log("BuySignal: Fired at : {0}".format(self.Time))
        self.buyOptions = 1

    # Buys a Call Option - 
    def BuyCall(self, slice):
        for i in slice.OptionChains:
            if i.Key != self.option_symbol: continue
            chain = i.Value

            # we sort the contracts to find OTM contract with farthest expiration
            contracts = sorted(sorted(sorted(chain, \
                key = lambda x: abs(chain.Underlying.Price - x.Strike)), \
                key = lambda x: x.Expiry, reverse=True), \
                key = lambda x: x.Right)
            
            if len(contracts) == 0: continue
            if contracts[0].AskPrice == 0: continue
            self.contract = contracts[0]

        # if found, trade it
        if self.contract:
            self.contractAmounts = int((self.portfolioRisk * self.Portfolio.Cash) / (self.contract.AskPrice * 100))
            if self.contractAmounts < 1:
                self.contractAmounts = 1
            self.contractDictionary[self.contract] = self.MarketOrder(self.contract.Symbol, self.contractAmounts).AverageFillPrice
            self.contractList.append(self.contract)
            self.buyOptions = 0
            self.contract = str()

    def OnOrderEvent(self, orderEvent):
        self.Log(str(orderEvent))
