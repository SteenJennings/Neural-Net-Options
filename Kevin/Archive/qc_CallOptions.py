# In this algorithm, we are importing a list of 'buy' dates from a github csv.
# We will purchase call options on these dates and sell them with a trailing stop-limit.
# Resources - https://www.quantconnect.com/forum/discussion/9482/simple-example-long-put-hedge/p1?ref=towm

import io
import requests
import pandas as pd
from datetime import timedelta
from QuantConnect.Data.Custom.CBOE import * # get pricing data

class WellDressedBlackLemur(QCAlgorithm):
    stopOrderTicket = None
    stopOrderFillTime = datetime.min
    highestContractPrice = 0

    def Initialize(self):
        # NOTE: QuantConnect provides equity options data from AlgoSeek going back as far as 2010.
        # The options data is available only in minute resolution, which means we need to consolidate
        # the data if we wish to work with other resolutions. 
        self.SetStartDate(2010, 1, 1)  # Set Start Date
        self.SetEndDate(2021, 5, 20) # Set End Date
        self.SetCash(1000000)  # Set Strategy Cash
        
        #Equity Info Here
        self.equity = self.AddEquity("AMD", Resolution.Minute)
        #Normalize data or calculations will be off
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.symbol = self.equity.Symbol
        
        # Options Contracts
        # initialize the option contract with empty string
        self.contract = str()
        # keep track of options contracts
        self.contractsAdded = set()
        self.buyOptions = 0 # buy signal
        self.lastOrderEvent = None
        
        # Buy/Sell Contract Criteria
        self.DaysBeforeExp = 5 # days before we close the options
        self.DTE = 15 # target contracts before expiration
        self.OTM = 0.05 # target OTM %
        self.contractAmounts = 50 # number of contracts to purchase
        
        # Schedule plotting function 30 minutes after every market open
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.Plotting)
                        
        # Download NN Buy Signals from Github Raw CSV and modify dataframes
        # - add month/day/year, filter df to predictions only, drop date and prediction columns
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/amd_predictions_05072021.csv"
        #self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/amzn_predictions_qc_052121.csv"
        df = pd.read_csv(io.StringIO(self.Download(self.url)))
        df[['month','day','year']] = df['date'].str.split("/", expand = True)
        df.columns = df.columns.str.lower()
        df = df[df['prediction'] == 1]
        df['year'] = df['year'].astype(int)
        df = df[df['year'] >= 2010]
        df = df.drop(columns=['date','prediction'])
        buyArray = df.to_numpy()
        
        # Next step is to iterate through each date and schedule a buy event
        for x in buyArray:
            # Schedule Buys - https://www.quantconnect.com/docs/algorithm-reference/scheduled-events
            self.Schedule.On(self.DateRules.On(int(x[2]), int(x[0]), int(x[1])), \
                            self.TimeRules.At(9,31), \
                            self.BuySignal)
        '''
        
        self.Schedule.On(self.DateRules.On(2010, 4, 23), \
                            self.TimeRules.At(9,31), \
                            self.BuySignal)
        '''
    def OnData(self, data):
        '''OnData event is the primary entry point for your algorithm. Each new data point will be pumped in here.
            Arguments:
                data: Slice object keyed by symbol containing the stock data
        '''
        if self.Portfolio.Cash > 30000 and self.buyOptions == 1:
            self.BuyCall(data)
        
        # close contract before it expires
        if self.contract:
            if(self.contract.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                self.Liquidate(self.contract)
                self.Log("Closed: too close to expiration")
                self.contract = str()
    
    # Sets 'Buy' Indicator to 1 - this will initiate a contract buy later
    def BuySignal(self):
        self.Log("BuySignal: Fired at : {0}".format(self.Time))
        self.buyOptions = 1
    
    # Buys a Call Option - 
    def BuyCall(self, data):
        if self.contract == str():
            # Retrieve options chain data
            self.contract = self.CallOptionsFilter(data)
            return
        elif self.contract == None:
            #self.Log("No Contracts: Fired at : {0}".format(self.Time))
            self.contract = str()
        # we must ensure the data passed to OnData has the contract as a key before placing a trade
        #elif not self.Portfolio[self.contract].Invested and data.ContainsKey(self.contract):
        elif data.ContainsKey(self.contract):
            ### Change this to buy contracts with a percentage of settled cash
            self.Buy(self.contract, self.contractAmounts)
            # Reset buy signal
            self.buyOptions = 0
            
    def CallOptionsFilter(self, data):
        '''
        The quantconnect api has multiple way to trade options.  The normal way is to set
        a filter and iterate over each option.  This can be slow so it is more efficient
        to get a list of the options contracts you're interested in and iterating through that.
        OptionChainProvider gets a list of option contracts for an underlying symbol at requested date.
        Then you can manually filter the contract list returned by GetOptionContractList.
        The manual filtering will be limited to the information included in the Symbol
        (strike, expiration, type, style) and/or prices from a History call.
        '''
        # note that the con of using the optionsChainProvider is you can't get Greeks or IV data
        
        contracts = self.OptionChainProvider.GetOptionContractList(self.symbol, data.Time)
        self.underlyingPrice = self.Securities[self.symbol].Price #save current stock price
        
        # filter the out-of-money options from the contract list which expire close to self.DTE number of days from now
        # Call options & less than 10% OTM & between 30/90 days   
        otm_calls = [i for i in contracts if i.ID.OptionRight == OptionRight.Call and
                                            i.ID.StrikePrice - self.underlyingPrice <= self.OTM * self.underlyingPrice and
                                            (self.DTE - 10)  < (i.ID.Date - data.Time).days < (self.DTE + 10)]
        
        # Sort options chain by DTE and OTM StrikePrice and add ONE to contract string
        if (len(otm_calls) > 0):
                contract = sorted(sorted(otm_calls, key = lambda x: abs((x.ID.Date - self.Time).days - self.DTE)),
                                                        key = lambda x: self.underlyingPrice - x.ID.StrikePrice)[0]
                if contract not in self.contractsAdded:
                    self.contractsAdded.add(contract)
                    self.AddOptionContract(contract, Resolution.Minute)
                    return contract
                elif contract in self.contractsAdded:
                    self.AddOptionContract(contract, Resolution.Minute)
                    return contract
                else:
                    return str()
            
    def Plotting(self):
        self.Plot("Data Chart", self.symbol, self.Securities[self.symbol].Close)
        
        option_invested = [x.Key for x in self.Portfolio if x.Value.Invested and x.Value.Type == SecurityType.Option]
        if option_invested:
            self.Plot("Data Chart", "strike", option_invested[0].ID.StrikePrice)
            
    def OnOrderEvent(self, orderEvent):
        # log order events
        # self.Log(str(orderEvent))
        
        #1. Write code to only act on fills
        if orderEvent.Status == OrderStatus.Filled:
            #2. Save the orderEvent to lastOrderEvent, use Debug to print the event OrderId
            self.lastOrderEvent = orderEvent
            self.Debug(orderEvent.OrderId)