############################################################################################################################### 
# Author: Kevin Tek
# FileName: qc_Call_StopLoss.py
# Class: Capstone Sprint 2021
# Description:  This loads predictions from a CSV and schedules buy dates 
#               for each prediction. The algorithm will purchase Call 
#               Options based on criteria such as % Out Of The Money (OTM), Min 
#               and Max Days To Expire (DTE), and portfolio risk profile.
#               After a contract is purchased, the algorithm closes (sells)  
#               the contract based on the risk criteria, which in this case is a 
#               combination of selling contracts a before expiration or 
#               utilizing a tight trailing stop loss based on each contract's 
#               AskPrice.  
#
# Resources: Some code was provided by QuantConnect BootCamps, Documents, Tutorials and Forums. See Below:
#   https://www.quantconnect.com/forum/discussion/9482/simple-example-long-put-hedge/p1?ref=towm
#   https://www.quantconnect.com/tutorials/introduction-to-options/quantconnect-options-api#QuantConnect-Options-API-Algorithm
#   https://www.quantconnect.com/docs/algorithm-reference/handling-data
#   https://www.quantconnect.com/tutorials/applied-options/iron-condor
#   https://www.quantconnect.com/learning/course/1/boot-camp-101-us-equities
#   https://www.quantconnect.com/docs/algorithm-reference/scheduled-events
#
###############################################################################################################################

from datetime import timedelta # to help calculate contract time
import pandas as pd # to create dataframes from CSV data
import io # to import CSV data
import requests # http requests for CSV data from GitHub RAW files

class NeuralNetworkTrailingStopLoss(QCAlgorithm):
    
    contractDictionary = {} # KVP to be used to track each contracts AskPrice 
                            # highs for trailing stop loss
    contractList = [] # track each purchased contract
    
    def Initialize(self):
        # Download NN Buy Signals/Predictions from Github Raw CSV - these will 
        # provide dates for us to purchase call options
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/Final_NN_Output/TSLA_pred_2021-05-30.csv"
        
        # modify dataframes
        df = pd.read_csv(io.StringIO(self.Download(self.url)))
        # split date column to three different columns for year, month and day 
        df[['year','month','day']] = df['date'].str.split("-", expand = True) 
        df.columns = df.columns.str.lower()
        df = df[df['prediction'] == 1]  # filter rows with predictions
        df['year'] = df['year'].astype(int) 
        df['month'] = df['month'].astype(int) 
        df['day'] = df['day'].astype(int) 
        # NOTE: QuantConnect only provides options data as far back as 2010
        df = df[df['year'] >= 2010]
        df = df.drop(columns=['date','prediction','expected','equal','correctbuysignal'])
        buyArray = df.to_numpy() # convert to array
        
        # NOTE: QuantConnect provides equity options data from AlgoSeek going 
        # back as far as 2010. The options data is available only in minute 
        # resolution, which means we need to consolidate the data if we wish to 
        # work with other resolutions. Start Dates and End Dates are based on 
        # the first and last dates from the NN CSV
        self.SetStartDate(buyArray[0][1], buyArray[0][2], buyArray[0][3])
        self.SetEndDate(buyArray[-1][1], buyArray[-1][2], buyArray[-1][3])
        self.SetCash(100000) # Starting Cash for our portfolio

        # Equity Info Here
        self.stockSymbol = str(buyArray[0][0]) # stock symbol here
        self.equity = self.AddEquity(self.stockSymbol, Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.option = self.AddOption(self.stockSymbol, Resolution.Minute )
        self.option_symbol = self.option.Symbol
        # use the underlying equity as the benchmark - we will see this graph
        # in the backtest results
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
        self.minPortfolioBalance = 10000 # stop if our balance gets this low
        self.stopLossPercentage = .015 # stop loss % for contract ask price
        
        # Iterate through the predictions and schedule a buy event at 9:31
        for x in buyArray:
            self.Schedule.On(self.DateRules.On(x[1], x[2], x[3]), \
                            self.TimeRules.At(9,31), \
                            self.BuySignal)
        
        # Schedule events everyday 5 minutes before the market closes          
        self.Schedule.On(self.DateRules.EveryDay(self.option_symbol), \
                 self.TimeRules.BeforeMarketClose(self.option_symbol, 5), \
                 self.EveryDayBeforeMarketClose)

    def OnData(self,slice):
        # OnData event is the primary entry point for your algorithm. Each new 
        # data point will be pumped in here.
        
        otmContractLimit = int(self.equity.Price * self.OTM) # max OTM Strike
        # set our strike/expiry filter for this option chain
        # (min spaces below current price, max spaces above current price, 
        #                       closest contract date, furthest contract date)
        self.option.SetFilter(0, otmContractLimit, timedelta(self.MinDTE), timedelta(self.MaxDTE))
        
        if self.Portfolio.Cash > self.minPortfolioBalance and self.buyOptions == 1:
            self.BuyCall(slice)
    
    # Checks contract expiration dates and Stop Loss every day before the market closes
    def EveryDayBeforeMarketClose(self):
        if self.contractList:
            for i in self.contractList:
                # check if the contract is close to expiration
                if(i.Symbol.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                    self.Liquidate(i.Symbol, "Liquidate: Close to Expiration")
                    self.Log("Closed: too close to expiration")
                    self.contractList.remove(i) # remove the contract from our list
                # update each contracts highest ask price
                elif self.Securities[i.Symbol].AskPrice > self.contractDictionary[i]:
                    self.Log("Contract AskPrice is higher, update stop loss")
                    # Save the new AskPrice high then update the stop loss %
                    self.contractDictionary[i] = self.Securities[i.Symbol].AskPrice
                    self.stopLossPercentage = self.stopLossPercentage * 2
                    self.Log(self.stockSymbol + "- NewHigh: " + str(self.contractDictionary[i]) + \
                               " Stop: " + str(round((self.contractDictionary[i] * (1-self.stopLossPercentage)),2)))
                # sell our contract(s) if we hit our stop loss
                elif self.Securities[i.Symbol].AskPrice <= round((self.contractDictionary[i] * (1-self.stopLossPercentage)),2):
                    self.Liquidate(i.Symbol, "Liquidate: Stop Loss")
                    self.Log("Stop Loss Hit")
                    self.contractList.remove(i) # remove the contract from our list
                    self.stopLossPercentage = .015 # reset stop loss
        else: return

    # Sets the 'Buy' Indicator to 1
    def BuySignal(self):
        self.Log("BuySignal: Fired at : {0}".format(self.Time))
        self.buyOptions = 1

    # Receives our options chain data, sorts the options contracts and purchases
    # the contract
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

        # if found, purchase the contract
        if self.contract:
            self.contractAmounts = int((self.portfolioRisk * self.Portfolio.Cash) / (self.contract.AskPrice * 100))
            if self.contractAmounts < 1:
                self.contractAmounts = 1
            # save the contract and average fill price as a KVP
            self.contractDictionary[self.contract] = self.MarketOrder(self.contract.Symbol, self.contractAmounts).AverageFillPrice
            # add the contract to our list so we can update the contract in 
            # the future (sell contract, update askPrice, etc.)
            self.contractList.append(self.contract)
            self.buyOptions = 0 # reset our buy signal
            self.contract = str()

    # All OrderEvents are logged here
    def OnOrderEvent(self, orderEvent):
        self.Log(str(orderEvent))
