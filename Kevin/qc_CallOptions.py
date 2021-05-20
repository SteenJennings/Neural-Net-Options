class WellDressedBlackLemur(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2020, 4, 13)  # Set Start Date
        self.SetEndDate(2021, 4, 26) # Set End Date
        self.SetCash(1000000)  # Set Strategy Cash
        
        #Equity Info Here
        self.equity = self.AddEquity("TSLA", Resolution.Minute)
        #Normalize data or calculations will be off
        self.equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.symbol = self.equity.Symbol
        
        # Options Contracts
        # initialize the option contract with empty string
        self.contract = str()
        # keep track of options contracts so we don't add the same contracts multiple times
        self.contractsAdded = set()
        self.buyOptions = 0 # buy signal
        
        # Buy/Sell Contract Criteria
        self.DaysBeforeExp = 5 # days before we close the options
        self.DTE = 60 # target contracts before expiration
        self.OTM = 0.10 # target OTM %
        self.percentage = 0.05 # percent of portfolio
        self.contractAmounts = 10 # number of contracts to purchase
        
        # Schedule plotting function 30 minutes after every market open
        self.Schedule.On(self.DateRules.EveryDay(self.symbol), \
                        self.TimeRules.AfterMarketOpen(self.symbol, 30), \
                        self.Plotting)
                        
        # Download NN Buy Data
        self.url = "https://raw.githubusercontent.com/SteenJennings/Neural-Net-Options/master/Kevin/QuantCSV/amd_predictions_05072021.csv"
        csv = self.Download(self.url)
        
        # Schedule Buys
        self.Schedule.On(self.DateRules.On(2020, 4, 13), \
                        self.TimeRules.At(9,31), \
                        self.BuySignal)
        self.Schedule.On(self.DateRules.On(2020, 4, 14), \
                        self.TimeRules.At(9,31), \
                        self.BuySignal)
        self.Schedule.On(self.DateRules.On(2020, 4, 15), \
                        self.TimeRules.At(9,31), \
                        self.BuySignal)
        self.Schedule.On(self.DateRules.On(2020, 4, 16), \
                        self.TimeRules.At(9,31), \
                        self.BuySignal)
        self.Schedule.On(self.DateRules.On(2020, 4, 17), \
                        self.TimeRules.At(9,31), \
                        self.BuySignal)

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
        self.Log("SpecificTime: Fired at : {0}".format(self.Time))
        self.buyOptions = 1
    
    # Buys a Call Option - 
    def BuyCall(self, data):
        if self.contract == str():
            # Retrieve options chain data
            self.contract = self.CallOptionsFilter(data)
            return
        #elif not self.Portfolio[self.contract].Invested and data.ContainsKey(self.contract):
        elif data.ContainsKey(self.contract):
            ### Change this to buy contracts with a percentage of settled cash
            self.Buy(self.contract, self.contractAmounts)
            # Reset buy signal
            self.buyOptions = 0
            
    def CallOptionsFilter(self, data):
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
        self.underlyingPrice = self.Securities[self.symbol].Price #save current stock price
        
        # filter the out-of-money options from the contract list which expire close to self.DTE number of days from now
        # Call options & less than 10% OTM & between 30/90 days   
        otm_calls = [i for i in contracts if i.ID.OptionRight == OptionRight.Call and
                                            i.ID.StrikePrice - self.underlyingPrice <= self.OTM * self.underlyingPrice and
                                            self.DTE - 30 < (i.ID.Date - data.Time).days < self.DTE + 30]
        
        test = sorted(sorted(otm_calls, key = lambda x: abs((x.ID.Date - self.Time).days - self.DTE)),
                                                        key = lambda x: self.underlyingPrice - x.ID.StrikePrice)
        
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
        self.Log(str(orderEvent))