# In this algorithm, we are importing a list of 'buy' dates from a github csv.
# We will purchase call options on these dates and sell them with a simple
# trailing stop-limit.

from datetime import timedelta
from QuantConnect.Data.Custom.CBOE import * # get pricing data

from io import StringIO
import pandas as pd

class UglyRedDog(QCAlgorithm):
    
    # Order ticket for our stop order, Datetime when stop order was last hit
    stopMarketTicket = None
    stopMarketOrderFillTime = datetime.min
    highestContractPrice = 0

    # At the very start of the algorithm we call Initialize() to set up our strategy.  This is important to set up
    # here so it can be restarted easily.
    def Initialize(self):
        self.SetStartDate(1999, 12, 13)  # backtest Start Date
        self.SetEndDate(2021, 5, 7) # backtest End Date
        self.SetCash(100000)  # Starting capital
        
        # Save security object then set data normalization mode for that object
        # request minute data for AMD, note that this may affect when orders are filled.  For example, if you use
        # daily data, the order will not fill until the next morning
        self.equity = self.AddEquity("AMD", Resolution.Minute) 
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.symbol = self.equity.Symbol
        
        # In the future we could use Coarse Selection to help select equities
        # self.AddUniverse(self.CoarseSelectionFilter)
        
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/amd_predictions_05072021.csv"
        csv = self.Download(self.url)
        #df = pd.read_csv('csv')
        
        # initialize the option contract with empty string
        self.contract = str()
        # keep track of otpions contracts so we don't add contracts multiple times
        self.contractsAdded = set()
        
        self.DaysBeforeExp = 2 #days before we close the options
        self.DTE = 40 #target contracts before expiration
        self.OTM = 0.05 # target OTM %
        self.percentage = 0.9 # percent of portfolio
        
        # this is a Momentum Percent Indicator
        self.spyMomentum = self.MOMP("SPY", 50, Resolution.Daily)
        
        # This will hlep measure the impact of our algorithm.  SPY will act as our benchmark.
        self.SetBenchmark("SPY")
        
        # Warm up algorithm for 50 days to populate the indicators prior to the start date - should be used in Initialize()
        # if you warm up, be sure to set a conditional flag in the OnData function to ensure
        # everything is ready (warmed up) prior to any other actions
        self.SetWarmup(50)
    
        # Schedule plotting function 30 minutes after every market open
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.Plotting)
                        
        '''
        Consider looping over the csv using itertuples to access dates and symbol...
        for bar in history.itertuples():
            self.fast.Update(bar.Index[1], bar.close)
            self.slow.Update(bar.Index[1], bar.close)
        '''
        
        # Schedule Call Options purchases 1 minute after market open
        self.Schedule.On(Self.DateRules.EveryDay("SYMBOL"),self.TimeRules.AfterMarketOpen("SYMBOL", 1), self.BuyCall)
    
    def Parse(self,url):
        # download file from url as string
        csv = self.Download(url).split("\n")
        
        # remove formatting characters
        buyDates = [x.replace("\r","").replace(" ","").replace("/","") for x in csv]
        
        # parse data into dictionary
        for arr in buyDates:
            buyDates = datetime.strptime(arr[0], "%m%d%Y").date()
            
        return arr

    def OnData(self, data):
        '''OnData event is the primary entry point for your algorithm. Each new data point will be pumped in here.
            Arguments:
                data: Slice object keyed by symbol containing the stock data
        '''
        if not self.SetWarmup.IsReady or self.IsWarmingUp:
            return
        
        # Algorithm Time - we can use this to trade during specific times
        # if self.Time.weekday() == 1:
        
        getDates = self.Parse(self.url)
        # if prediction date, buy calls
        for date in getDates:
            if date == self.Time:
                self.BuyCall(data)

        # close call before it expires
        # in the future, we will need to change this to a trailing stop loss
        if self.contract:
            if(self.contract.ID.Date - self.Time) <= timedelta(self.DaysBeforeExp):
                self.Liquidate(self.contract)
                self.Log("Closed: too close to expiration")
                self.contract = str()
            '''
            else:
                if self.Securities["AMD"].Close > self.highestContractPrice:
                    self.highestContractPrice = self.Securities["AMD"].Close
                    updateFields = UpdateOrderFields()
                    updateFields.StopPrice = self.highestSPYPrice * 0.9
                    self.stopMarketTicket.Update(updateFields)
            '''
            
        #Liquidate and Set Holdings
        #self.Liquidate("Equity Here")
        #self.SetHoldings("Equity Here")
                
        # Utilize self.Debug to display data
        # self.Debug(self.Portfolio["AMD"].AveragePrice)
        
    def BuyCall(self, data):
        self.Buy(self.contract, 10)  # Buy calls - in the future, we'll add more conditional statements
            
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
        self.underlyingPrice = self.Securities[self.symbol].Price #safe current price
        
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
