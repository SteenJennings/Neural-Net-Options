from Alphas.HistoricalReturnsAlphaModel import HistoricalReturnsAlphaModel
from Execution.StandardDeviationExecutionModel import StandardDeviationExecutionModel
from Portfolio.EqualWeightingPortfolioConstructionModel import (
    EqualWeightingPortfolioConstructionModel,
)
from Selection.QC500UniverseSelectionModel import QC500UniverseSelectionModel


class EMAMomentumUniverse(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 1, 7)
        self.SetEndDate(2021, 4, 26)
        self.SetCash(100000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.AddUniverse(self.CoarseSelectionFunction)
        self.averages = {}

    def CoarseSelectionFunction(self, universe):
        selected = []
        universe = sorted(universe, key=lambda c: c.DollarVolume, reverse=True)
        universe = [c for c in universe if c.Price > 25 and c.DollarVolume > 100000000][
            :100
        ]

        for coarse in universe:
            symbol = coarse.Symbol

            if symbol not in self.averages:
                # 1. Call history to get an array of 200 days of history data
                history = self.History(symbol, 15, Resolution.Daily)

                # 2. Adjust SelectionData to pass in the history result
                self.averages[symbol] = SelectionData(history)

            self.averages[symbol].update(self.Time, coarse.AdjustedPrice)

            if (
                self.averages[symbol].is_ready()
                and self.averages[symbol].fast > self.averages[symbol].slow
            ):
                selected.append(symbol)

        return selected[:10]

    def OnSecuritiesChanged(self, changes):
        # Save securities changed as self.changes
        self.changes = changes
        # Log the changes in the function
        self.Log(f"OnSecuritiesChanged({self.Time}):: {changes}")
        for security in changes.RemovedSecurities:
            self.Liquidate(security.Symbol)

        for security in changes.AddedSecurities:
            self.SetHoldings(security.Symbol, 0.10)
            # spy_option.SetFilter(-2, +5, timedelta(days=7), timedelta(days=30)) ---- This code handles pulling options data


class SelectionData:
    # 3. Update the constructor to accept a history array
    def __init__(self, history):
        self.slow = ExponentialMovingAverage(15)
        self.fast = ExponentialMovingAverage(5)
        # 4. Loop over the history data and update the indicators
        for bar in history.itertuples():
            self.fast.Update(bar.Index[1], bar.close)
            self.slow.Update(bar.Index[1], bar.close)

    def is_ready(self):
        return self.slow.IsReady and self.fast.IsReady

    def update(self, time, price):
        self.fast.Update(time, price)
        self.slow.Update(time, price)
