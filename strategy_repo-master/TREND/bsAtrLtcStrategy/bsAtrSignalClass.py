import talib as ta
import numpy as np
import pandas as pd

"""
将kdj策略需要用到的信号生成器抽离出来
"""

class bsAtrSignal():

    def __init__(self):
        self.author = 'channelCMT'

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

    #### 计算ADX指标
    def adxEnvV2(self,am,paraDict):
        adxPeriod = paraDict["adxPeriod"]
        adxMaPeriod = paraDict["adxMaPeriod"]
        adxLowThreshold = paraDict["adxLowThreshold"]
        adxMaxThreshold = paraDict["adxMaxThreshold"]

        adxTrend = ta.ADX(am.high, am.low, am.close, adxPeriod)
        adxMa = ta.MA(adxTrend, adxMaPeriod)

        adxSmall = adxTrend[-1]<=adxLowThreshold
        adxDowning = adxTrend[-1]<adxMa[-1]
        adxBig = adxTrend[-1]>=adxMaxThreshold

        # Status
        if adxSmall or adxDowning or adxBig:
            adxCanTrade = -1
        else:
            adxCanTrade = 1
        return adxCanTrade, adxTrend

    def atrWideBand(self, am, paraDict):
        atrPeriod = paraDict['atrPeriod']
        smaPeriod = paraDict['smaPeriod']
        lmaPeriod = paraDict['lmaPeriod']
        atrSmallMultiplier = paraDict['atrSmallMultiplier']
        atrBigMultiplier = paraDict['atrBigMultiplier']

        atr = ta.ATR(am.high,am.low, am.close, atrPeriod)
        sma = ta.MA(am.close, smaPeriod, 1)
        lma = ta.MA(am.close, lmaPeriod, 0)

        priceDirection = 1 if sma[-1]>lma[-1] else -1
        upperBand = sma+atrSmallMultiplier*atr if priceDirection==1 else sma+atrBigMultiplier*atr
        lowerBand = sma-atrSmallMultiplier*atr if priceDirection==-1 else sma-atrBigMultiplier*atr

        return upperBand, lowerBand, sma, lma
    
    def atrNorrowBand(self, am, paraDict):
        atrPeriod = paraDict['atrPeriod']
        smaPeriod = paraDict['smaPeriod']
        lmaPeriod = paraDict['lmaPeriod']
        atrSmallMultiplier = paraDict['atrSmallMultiplier']/2
        atrBigMultiplier = paraDict['atrBigMultiplier']/2

        atr = ta.ATR(am.high,am.low, am.close, atrPeriod)
        sma = ta.MA(am.close, smaPeriod, 1)
        lma = ta.MA(am.close, lmaPeriod, 0)

        priceDirection = 1 if sma[-1]>lma[-1] else -1
        upperBand = sma+atrSmallMultiplier*atr if priceDirection==1 else sma+atrBigMultiplier*atr
        lowerBand = sma-atrSmallMultiplier*atr if priceDirection==-1 else sma-atrBigMultiplier*atr

        return upperBand, lowerBand, sma, lma

    def atrExitSmaBand(self, am, paraDict):
        atrPeriod = paraDict['atrPeriod']
        smaPeriod = paraDict['smaPeriod']
        atrSmallMultiplier = paraDict['atrSmallMultiplier']/4

        atr = ta.ATR(am.high,am.low, am.close, smaPeriod)
        sma = ta.MA(am.close, smaPeriod, 1)
        upperBand = sma+atrSmallMultiplier*atr
        lowerBand = sma-atrSmallMultiplier*atr
        return upperBand, lowerBand, sma
    
    def atrExitLmaBand(self, am, paraDict):
        atrPeriod = paraDict['atrPeriod']
        lmaPeriod = paraDict['lmaPeriod']
        atrSmallMultiplier = paraDict['atrSmallMultiplier']/4

        atr = ta.ATR(am.high,am.low, am.close, atrPeriod)
        lma = ta.MA(am.close, lmaPeriod, 0)
        upperBand = lma+atrSmallMultiplier*atr
        lowerBand = lma-atrSmallMultiplier*atr
        return upperBand, lowerBand, lma

    def fliterVol(self, am, paraDict):
        volPeriod = paraDict['volPeriod']
        lowVolThreshold = paraDict['lowVolThreshold']
        std = ta.STDDEV(am.close, volPeriod)
        atr = ta.ATR(am.high, am.low, am.close, volPeriod)
        rangeHL = (ta.MAX(am.high, volPeriod)-ta.MIN(am.low, volPeriod))/2
        minVol = min(std[-1], atr[-1], rangeHL[-1])
        lowFilterRange = am.close[-1]*lowVolThreshold
        maxVol = max(std[-1], atr[-1], rangeHL[-1])

        filterCanTrade = 1 if minVol >= lowFilterRange else -1
        return filterCanTrade

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

    def filterPatternV(self, am, paraDict):
        atrPeriod = paraDict['atrPeriod']
        filterRctV = paraDict['filterRctV']

        filterRangePct = (ta.MAX(am.high, atrPeriod)[-1] - ta.MIN(am.low, atrPeriod)[-1])/am.close[-1]

        if filterRangePct>=filterRctV:
            filterVCanTrade = -1
        else:
            filterVCanTrade = 1
        return filterVCanTrade