# Testing Alternate Options

from clr import AddReference
AddReference("System")
AddReference("QuantConnect.Algorithm")
AddReference("QuantConnect.Common")

from System import *
from QuantConnect import *
from QuantConnect.Algorithm import *
from datetime import timedelta

class BasicTemplateOptionsAlgorithm(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2018, 1, 1)
        self.SetEndDate(2018, 2, 10)
        self.SetCash(100000)

        self.option = self.AddOption("AMD")
        self.option_symbol = self.option.Symbol
        self.contract = str()
        self.DaysBeforeExp = 2
        self.buyOptions = 0
        
        # set our strike/expiry filter for this option chain
        #option.SetFilter(0, +20, timedelta(0), timedelta(5))

        # use the underlying equity as the benchmark
        self.SetBenchmark("GOOG")
        
        self.Schedule.On(self.DateRules.On(2018, 1, 10), \
                            self.TimeRules.At(9,31), \
                            self.BuySignal)
        self.Schedule.On(self.DateRules.On(2018, 1, 25), \
                            self.TimeRules.At(9,31), \
                            self.BuySignal)

    def OnData(self,slice):
        
        # set our strike/expiry filter for this option chain
        self.option.SetFilter(0, +10, timedelta(7), timedelta(15))
        
        if self.Portfolio.Cash > 30000 and self.buyOptions == 1:
            self.BuyCall(slice)
            
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
    def BuyCall(self, slice):
        for kvp in slice.OptionChains:
            if kvp.Key != self.option_symbol: continue
            chain = kvp.Value

            # we sort the contracts to find at the money (ATM) contract with farthest expiration
            contracts = sorted(sorted(sorted(chain, \
                key = lambda x: abs(chain.Underlying.Price - x.Strike)), \
                key = lambda x: x.Expiry, reverse=True), \
                key = lambda x: x.Right)
            
            if len(contracts) == 0: continue
            self.contract = contracts[0].Symbol

        # if found, trade it
        if self.contract:
            self.Buy(self.contract, 1)
            self.buyOptions = 0
            #self.MarketOnCloseOrder(symbol, -1)

    def OnOrderEvent(self, orderEvent):
        self.Log(str(orderEvent))