from datetime import timedelta
#below gets pricing data from CBOE
from QuantConnect.Data.Custom.CBOE import *

class WellDressedFluorescentOrangeBarracuda(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2020, 4, 26)  # Set Start Date
        self.SetEndDate(2021, 4, 26) # Set End Date
        self.SetCash(100000)  # Set Strategy Cash
        self.equity = self.AddEquity("TSLA", Resolution.Minute) # add the asset
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.symbol = self.equity.Symbol
        
        #add vix data
        self.vix = self.AddData(CBOE, "VIX").Symbol
        # initialize the IV indicator
        self.rank = 0
        # initialize the option contract with empty string
        self.contract = str()
        # keep track of otpions contracts so we don't add contracts multiple times
        self.contractsAdded = set()
        
        self.DaysBeforeExp = 3 #days before we close the options
        self.DTE = 60 #target contracts before expiration
        self.OTM = 0.10 # target OTM %
        self.lookbackIV = 25 # days we'll be looking into the past IV
        self.IVlvl = 0.25 # signal for IV level to purchase contracts
        self.percentage = 0.05 # percent of portfolio
        
        # Schedule plotting function 30 minutes after every market open
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.Plotting)
        # Schedule VIX Rank function 30 minutes after every market open
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.VIXRank)
        # warmup for IV indicator of data.
        # The warm-up period is used for algorithms using the technical indicators.
        # pumps data in
        self.SetWarmUp(timedelta(self.lookbackIV))
    
    
    def VIXRank(self):
        history = self.History(CBOE, self.vix, self.lookbackIV, Resolution.Daily)
        # (current - Min) / (max - min)
        self.rank = ((self.Securities[self.vix].Price - min(history[:-1]["low"])) / (max(history[:-1]["high"] - min(history["low"]))))

    def OnData(self, data):
        '''OnData event is the primary entry point for your algorithm. Each new data point will be pumped in here.
            Arguments:
                data: Slice object keyed by symbol containing the stock data
        '''
        if self.IsWarmingUp:
            return
        
        # buy put if VIX is relatively high    
        if self.rank > self.IVlvl:
            #self.BuyPut(data)
            self.BuyCall(data)
        
        # close put before it expires
        if self.contract:
            if(self.contract.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                self.Liquidate(self.contract)
                self.Log("Closed: too close to expiration")
                self.contract = str()
            
    def BuyCall(self, data):
        if self.contract == str():
            self.contract = self.OptionsFilter(data)
            return
        elif not self.Portfolio[self.contract].Invested and data.ContainsKey(self.contract):
            #buy with percentage of settled cash
            self.Buy(self.contract, 20)
    
    def OptionsFilter(self, data):
        ''' The quantconnect api has multiple way to trade options.  The normal way is to set
            a filter and iterate over each option.  This can be slow so it is more efficient
            to get a list of the options contracts you're interested in and iterating through
            that.'''
        ''' OptionChainProvider gets a list of option contracts for an underlying symbol at requested date.
            Then you can manually filter the contract list returned by GetOptionContractList.
            The manual filtering will be limited to the information included in the Symbol
            (strike, expiration, type, style) and/or prices from a History call '''
        # note that the con of using the optionsChainProvider is you can't get Greeks or IV data
        
        contracts = self.OptionChainProvider.GetOptionContractList(self.symbol, data.Time)
        self.underlyingPrice = self.Securities[self.symbol].Price #save current price
        
        #filter the out-of-money put options from the contract list which expire close to self.DTE number of days from now
                                            
        otm_calls = [i for i in contracts if i.ID.OptionRight == OptionRight.Call and
                                            i.ID.StrikePrice - self.underlyingPrice <= self.OTM * self.underlyingPrice and
                                            self.DTE - 30 < (i.ID.Date - data.Time).days < self.DTE + 30]
        
        if (len(otm_calls) > 0):
            contract = sorted(sorted(otm_calls, key = lambda x: abs((x.ID.Date - self.Time).days - self.DTE)),
                                                    key = lambda x: self.underlyingPrice - x.ID.StrikePrice)[0]
            if contract not in self.contractsAdded:
                self.contractsAdded.add(contract)
                self.AddOptionContract(contract, Resolution.Minute)
            return contract
        else:
            return str()
            
    def Plotting(self):
        # plot takes 3 arguements, name, name, data
        self.Plot("Vol Chart", "Rank", self.rank)
        
        self.Plot("Vol Chart", "lvl", self.IVlvl)
        
        self.Plot("Data Chart", self.symbol, self.Securities[self.symbol].Close)
        
        option_invested = [x.Key for x in self.Portfolio if x.Value.Invested and x.Value.Type == SecurityType.Option]
        if option_invested:
            self.Plot("Data Chart", "strike", option_invested[0].ID.StrikePrice)
            
    def OnOrderEvent(self, orderEvent):
        # log order events
        self.Log(str(orderEvent))