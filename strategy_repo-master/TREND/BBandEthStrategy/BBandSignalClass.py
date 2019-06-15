import talib as ta
import numpy as np
import pandas as pd

"""
将kdj策略需要用到的信号生成器抽离出来
"""

class BBandSignal:

    def __init__(self):
        self.author = 'channel'

    #### 计算ADX指标
    def adxEnv(self,am,paraDict):
        adxPeriod = paraDict["adxPeriod"]
        adxMaxPeriod = paraDict["adxMaxPeriod"]
        adxHighthreshold = paraDict["adxHighthreshold"]
        adxLowthreshold = paraDict["adxLowthreshold"]

        adxTrend = ta.ADX(am.high, am.low, am.close, adxPeriod)
        adxMax = ta.MAX(adxTrend, adxMaxPeriod)

        # Status
        if ((adxTrend[-1]<=adxHighthreshold) and (adxMax[-1]> adxHighthreshold)) \
        or (adxTrend[-1]<=adxLowthreshold):
            adxCanTrade = -1
        else:
            adxCanTrade = 1
        return adxCanTrade, adxTrend

        ### 计算ER指标
    def corAdd(self, am, paraDict):
        corPeriod = paraDict['corPeriod']
        maCorPeriod = paraDict['maCorPeriod']

        corLowVolume = ta.CORREL(ta.MA(am.low, corPeriod), ta.MA(am.volume, corPeriod), corPeriod)
        corHighVolume = ta.CORREL(ta.MA(am.high, corPeriod), ta.MA(am.volume, corPeriod), corPeriod)
        maCorLV = ta.MA(corLowVolume, maCorPeriod)
        maCorHV = ta.MA(corHighVolume, maCorPeriod)
        corUp = corLowVolume[-1]>maCorLV[-1]
        corDn = corHighVolume[-1]<maCorHV[-1]

        if corUp:
            corCanAddPos = 1
        elif corDn:
            corCanAddPos = -1
        else:
            corCanAddPos = 0
        return corCanAddPos

    def bBandEntrySignal(self, am, paraDict):
        bBandShortPeriod = paraDict['bBandShortPeriod']
        bBandLongPeriod = paraDict['bBandLongPeriod']
        bBandEntry = paraDict['bBandEntry']

        bBandShortEntryUp, bBandShortEntryMa, bBandShortEntryDn = ta.BBANDS(am.close, bBandShortPeriod, bBandEntry, bBandEntry)
        bBandLongEntryUp, bBandLongEntryMa, bBandLongEntryDn = ta.BBANDS(am.close, bBandLongPeriod, bBandEntry, bBandEntry)

        return bBandShortEntryUp, bBandShortEntryMa, bBandShortEntryDn, bBandLongEntryUp, bBandLongEntryMa, bBandLongEntryDn

    def bBandExitSignal(self, am, paraDict):
        bBandShortPeriod = paraDict['bBandShortPeriod']
        bBandLongPeriod = paraDict['bBandLongPeriod']
        bBandExit = paraDict['bBandExit']

        bBandShortExitUp, bBandShortExitMa, bBandShortExitDn = ta.BBANDS(am.close, bBandShortPeriod, bBandExit, bBandExit)
        bBandLongExitUp, bBandLongExitMa, bBandLongExitDn = ta.BBANDS(am.close, bBandLongPeriod, bBandExit, bBandExit)
        return bBandShortExitUp, bBandShortExitDn , bBandLongExitUp, bBandLongExitDn

    def fliterVol(self, am, paraDict):
        volPeriod = paraDict['volPeriod']
        lowVolThreshold = paraDict['lowVolThreshold']
        highVolThreshold= paraDict['highVolThreshold']
        std = ta.STDDEV(am.close, volPeriod)
        atr = ta.ATR(am.high, am.low, am.close, volPeriod)
        rangeHL = ta.MAX(am.high, volPeriod)-ta.MIN(am.low, volPeriod)
        minVol = min(std[-1], atr[-1], rangeHL[-1])
        lowFilterRange = am.close[-1]*lowVolThreshold
        maxVol = max(std[-1], atr[-1], rangeHL[-1])
        highFilterRange = am.close[-1]*highVolThreshold

        filterCanTrade = 1 if minVol >= lowFilterRange else -1
        highVolPos = 1 if maxVol >= highFilterRange else -1
        return filterCanTrade, highVolPos