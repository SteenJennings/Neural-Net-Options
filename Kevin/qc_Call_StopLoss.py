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
    
    # Order ticket for our stop order, Datetime when stop order was last hit
    stopMarketTicket = None
    stopMarketFillTime = datetime.min
    highestContractPrice = 0 # we will need this for the trailing stop loss
    
    def Initialize(self):
        # NOTE: QuantConnect provides equity options data from AlgoSeek going back as far as 2010.
        # The options data is available only in minute resolution, which means we need to consolidate
        # the data if we wish to work with other resolutions.
        self.SetStartDate(2012, 1, 1)
        self.SetEndDate(2013, 1, 1)
        self.SetCash(100000) # Starting Cash for our portfolio

        # Equity Info Here
        self.equity = self.AddEquity("AMZN", Resolution.Minute)
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.option = self.AddOption("AMZN")
        self.option_symbol = self.option.Symbol
        # use the underlying equity as the benchmark
        #self.SetBenchmark(self.option_symbol)
        
        # Option Contracts
        self.contract = str()
        self.buyOptions = 0 # buy signal
        self.DaysBeforeExp = 1 # close the options this many days before expiration
        self.OTM = 0.10 # target OTM %
        self.MinDTE = 10 # contract minimum DTE
        self.MaxDTE = 20 # contract maximum DTE
        self.contractAmounts = 1 # number of contracts to purchase
        self.portfolioRisk = 0.1 # percentage of portfolio to be used for purchases
        
        # Download NN Buy Signals from Github Raw CSV
        #self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/amd_predictions_05072021.csv"
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/amzn_predictions_qc_052121.csv"
        
        # modify dataframes add month/day/year, filter df to predictions only, drop date and 
        # prediction columns
        df = pd.read_csv(io.StringIO(self.Download(self.url)))
        df[['month','day','year']] = df['date'].str.split("/", expand = True)
        df.columns = df.columns.str.lower()
        df = df[df['prediction'] == 1]
        df['year'] = df['year'].astype(int)
        df = df[df['year'] == 2012]
        df = df.drop(columns=['date','prediction'])
        buyArray = df.to_numpy()
        
        # Next step is to iterate through the predictions and schedule a buy event
        for x in buyArray:
            # Schedule Buys - https://www.quantconnect.com/docs/algorithm-reference/scheduled-events
            self.Schedule.On(self.DateRules.On(int(x[2]), int(x[0]), int(x[1])), \
                            self.TimeRules.At(9,31), \
                            self.BuySignal)
        '''
        self.Schedule.On(self.DateRules.On(2012, 3, 20), \
                            self.TimeRules.At(9,31), \
                            self.BuySignal)
        '''

    def OnData(self,slice):
        # OnData event is the primary entry point for your algorithm. Each new data point will be pumped in here.
        
        otmContractLimit = int(self.equity.Price * self.OTM)

        # set our strike/expiry filter for this option chain
        self.option.SetFilter(0, otmContractLimit, timedelta(self.MinDTE), timedelta(self.MaxDTE))
        
        if self.Portfolio.Cash > 30000 and self.buyOptions == 1:
            self.BuyCall(slice)
        
        if self.contract:
            if(self.contract.Symbol.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                self.Liquidate(self.contract.Symbol)
                self.Log("Closed: too close to expiration")
                self.contract = str()
            
            ### I need to implement a Dictionary to be called in this function and BuyCall
            ### Dictionary will create KVP between contracts and highest contract prices
            '''
            elif self.contract.AskPrice > self.highestContractPrice:
                # Save the new high to highestContractPrice; then update the stop price 
                self.highestContractPrice = self.contract.AskPrice
                updateFields = UpdateOrderFields()
                updateFields.StopPrice = self.highestContractPrice * 0.75
                self.stopMarketTicket.Update(updateFields)
                
                # Print the new stop price with Debug()
                self.Debug("SPY: " + str(self.highestSPYPrice) + " Stop: " + str(updateFields.StopPrice))
            '''
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
            self.contract = contracts[0]

        # if found, trade it
        if self.contract:
            self.MarketOrder(self.contract.Symbol, self.contractAmounts)
            self.stopMarketTicket = self.StopMarketOrder(self.contract.Symbol, \
                                    -self.contractAmounts, 0.75 * self.contract.AskPrice)
            self.buyOptions = 0
            #self.MarketOnCloseOrder(symbol, -1)

    def OnOrderEvent(self, orderEvent):
        #self.Log(str(orderEvent))
        
        # Check if we hit our stop loss (Compare the orderEvent.Id with the stopMarketTicket.OrderId)
        # It's important to first check if the ticket isn't null (i.e. making sure it has been submitted)
        if self.stopMarketTicket is not None and self.stopMarketTicket.OrderId == orderEvent.OrderId:
            # Store datetime
            self.stopMarketFillTime = self.Time