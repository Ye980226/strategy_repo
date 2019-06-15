import talib as ta
import numpy as np
import pandas as pd

"""
将kdj策略需要用到的信号生成器抽离出来
"""

class hlBreakSignal():

    def __init__(self):
        self.author = 'channel'

    #### 计算ADX指标
    def adxEnv(self,am,paraDict):
        adxPeriod = paraDict["adxPeriod"]
        adxMaxPeriod = paraDict["adxMaxPeriod"]
        adxHighThreshold = paraDict["adxHighThreshold"]
        adxLowThreshold = paraDict["adxLowThreshold"]

        adxTrend = ta.ADX(am.high, am.low, am.close, adxPeriod)
        adxMax = ta.MAX(adxTrend, adxMaxPeriod)

        # Status
        if ((adxTrend[-1]<=adxHighThreshold) and (adxMax[-1]> adxHighThreshold)) \
        or (adxTrend[-1]<=adxLowThreshold):
            adxCanTrade = -1
        else:
            adxCanTrade = 1
        return adxCanTrade, adxTrend

    def hlExitWideBand(self, am, paraDict):
        hlExitPeriod = paraDict['hlExitPeriod']

        highExitBand = ta.MAX(am.high, hlExitPeriod)
        lowExitBand = ta.MIN(am.low, hlExitPeriod)

        return highExitBand, lowExitBand
    
    def hlExitNorrowBand(self, am, paraDict):
        hlExitPeriod = paraDict['hlExitPeriod']//2

        highExitBand = ta.MAX(am.high, hlExitPeriod)
        lowExitBand = ta.MIN(am.low, hlExitPeriod)

        return highExitBand, lowExitBand

    def hlEntryWideBand(self, am, paraDict):
        hlEntryPeriod = paraDict['hlEntryPeriod']

        highEntryBand = ta.MAX(am.close, hlEntryPeriod)
        lowEntryBand = ta.MIN(am.close, hlEntryPeriod)
        return highEntryBand, lowEntryBand
    
    def hlEntryNorrowBand(self, am, paraDict):
        hlEntryPeriod = paraDict['hlEntryPeriod']//2

        highEntryBand = ta.MAX(am.close, hlEntryPeriod)
        lowEntryBand = ta.MIN(am.close, hlEntryPeriod)
        return highEntryBand, lowEntryBand

    def hlcVolumeSpike(self, am, paraDict):
        barCount = paraDict['barCount']

        volumePeriod = paraDict['volumePeriod']
        volumeSpikeTime = paraDict['volumeSpikeTime']
        priceSpikePct = paraDict['priceSpikePct']

        spikeThreshold = (ta.MA(am.volume, volumePeriod)+volumeSpikeTime * ta.STDDEV(am.volume, volumePeriod))[-1]
        hcPct = (ta.MAX(am.high, barCount)-ta.MIN(am.close, barCount))/am.close
        lcPct = (ta.MAX(am.close, barCount)-ta.MIN(am.low, barCount))/am.close
        # rsi = ta.RSI(am.close, volumePeriod)
        # overBought = rsi[-1]>75
        # overSold = rsi[-1]<25and overBought and overSold

        hcSpike = hcPct[-1]>priceSpikePct
        lcSpike = lcPct[-1]>priceSpikePct
        volumeSpike = ta.MAX(am.volume, barCount)[-1]> spikeThreshold

        spikeExit = 0
        spikeEntry = 0
        if volumeSpike:
            if hcSpike :
                spikeExit = 'exitLong'
                spikeEntry = 'entryShort'
            elif lcSpike:
                spikeExit = 'exitShort'
                spikeEntry = 'entryLong'
        return spikeExit



    ### 计算ER指标
    def erAdd(self, am, paraDict):
        changeVolatilityPeriod = paraDict['changeVolatilityPeriod']
        erSemaPeriod = paraDict['erSemaPeriod']
        erLemaPeriod = paraDict['erLemaPeriod']
        erThreshold = paraDict['erThreshold']

        # indicator
        change = np.abs(am.close[changeVolatilityPeriod:]-am.close[:-changeVolatilityPeriod])
        volatility = ta.SUM(np.abs(am.close[1:]-am.close[:-1]), changeVolatilityPeriod)
        er = change[-120:]/volatility[-120:]
        erSma = ta.EMA(er, erSemaPeriod)
        erLma = ta.MA(er, erLemaPeriod)

        # condition
        erUp = (erSma[-1]>erLma[-1])
        erThreshold = (erSma[-1]>erThreshold)

        erCanAddPos = True if erUp and erThreshold else False
        return erCanAddPos, erSma, erLma

    def fliterVol(self, am, paraDict):
        volPeriod = paraDict['volPeriod']
        lowVolThreshold = paraDict['lowVolThreshold']
        highVolThreshold= paraDict['highVolThreshold']
        std = ta.STDDEV(am.close, volPeriod)
        atr = ta.ATR(am.high, am.low, am.close, volPeriod)
        rangeHL = (ta.MAX(am.high, volPeriod)-ta.MIN(am.low, volPeriod))/2
        minVol = min(std[-1], atr[-1], rangeHL[-1])
        lowFilterRange = am.close[-1]*lowVolThreshold
        maxVol = max(std[-1], atr[-1], rangeHL[-1])
        highFilterRange = am.close[-1]*highVolThreshold

        filterCanTrade = 1 if minVol >= lowFilterRange else -1
        highVolPos = 1 if maxVol >= highFilterRange else -1
        return filterCanTrade, highVolPos

    def filterNorrowPatternV(self, am, paraDict):
        hlEntryPeriod = paraDict['hlEntryPeriod']//2
        filterRctV = paraDict['filterRctV']

        arrayRange = am.close[-hlEntryPeriod:-1]

        highIndex = np.where(arrayRange == arrayRange[np.argmax(arrayRange)])[0][-1]
        lowIndex = np.where(arrayRange == arrayRange[np.argmin(arrayRange)])[0][-1]
        
        highLowPeriod = int(hlEntryPeriod - highIndex)
        lowHighPeriod = int(hlEntryPeriod - lowIndex)
        filterHighPct = (ta.MAX(am.close, highLowPeriod)[-1] - ta.MIN(am.low, highLowPeriod)[-1])/am.close[-1]
        filterLowPct =  (ta.MAX(am.high, lowHighPeriod)[-1] - ta.MIN(am.close, lowHighPeriod)[-1])/am.close[-1]

        if (filterHighPct>=filterRctV) or (filterLowPct>=filterRctV):
            filterVCanTrade = -1
        else:
            filterVCanTrade = 1
        return filterVCanTrade

    def filterWidePatternV(self, am, paraDict):
        hlEntryPeriod = paraDict['hlEntryPeriod']
        filterRctV = paraDict['filterRctV']

        arrayRange = am.close[-hlEntryPeriod:-1]

        highIndex = np.where(arrayRange == arrayRange[np.argmax(arrayRange)])[0][-1]
        lowIndex = np.where(arrayRange == arrayRange[np.argmin(arrayRange)])[0][-1]

        highLowPeriod = int(hlEntryPeriod - highIndex)
        lowHighPeriod = int(hlEntryPeriod - lowIndex)
        filterHighPct = (ta.MAX(am.close, highLowPeriod)[-1] - ta.MIN(am.low, highLowPeriod)[-1])/am.close[-1]
        filterLowPct =  (ta.MAX(am.high, lowHighPeriod)[-1] - ta.MIN(am.close, lowHighPeriod)[-1])/am.close[-1]

        if (filterHighPct>=filterRctV) or (filterLowPct>=filterRctV):
            filterVCanTrade = -1
        else:
            filterVCanTrade = 1
        return filterVCanTrade