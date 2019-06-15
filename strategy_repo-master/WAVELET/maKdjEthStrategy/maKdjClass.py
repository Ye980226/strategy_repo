import talib as ta
import numpy as np
import pandas as pd

"""
将kdj策略需要用到的信号生成器抽离出来
"""

class maKdjSignal():

    def __init__(self):
        self.author = 'channel'

    ### 计算MA指标
    def maSignal(self, am, paraDict):
        trendDirection = 0
        maPeriod = paraDict["maPeriod"]
        maType = paraDict["maType"]
        trendMa = ta.MA(am.close, maPeriod, matype=maType)
        if (trendMa[-1]>trendMa[-2]):
            trendDirection = 1
        elif (trendMa[-1]<trendMa[-2]):
            trendDirection = -1
        return trendDirection, trendMa

    def kdjSignal(self, am, paraDict):
        fastkPeriod = paraDict["fastkPeriod"]
        slowkPeriod = paraDict["slowkPeriod"]
        slowkMaType = paraDict["slowkMaType"]
        slowdPeriod = paraDict["slowdPeriod"]
        slowdMaType = paraDict["slowdMaType"]

        k, d = ta.STOCH(am.high, am.low, am.close, fastkPeriod, slowkPeriod, slowkMaType, slowdPeriod, slowdMaType)
        return k, d
    

    def volumeFilter(self, am, paraDict):
        vstdLongPeriod = paraDict['vstdLongPeriod']
        vstdShortPeriod = paraDict['vstdShortPeriod']
        # nVbDev = paraDict['nVbDev']
        # vbMaType = paraDict['vbMaType']
        # volumeUpper, volumeClose, volumeLower = ta.BBANDS(am.volume, vbPeriod, nVbDev, nVbDev, vbMaType)
        vstdShort = ta.STDDEV(am.volume, vstdShortPeriod)        
        vstdLong = ta.STDDEV(am.volume, vstdLongPeriod)
        volumeUp = 1 if vstdShort[-1]>vstdLong[-1] else -1
        return volumeUp, vstdShort, vstdLong

    def fliterVol(self, am, paraDict):
        volPeriod = paraDict['volPeriod']
        lowVolThreshold = paraDict['lowVolThreshold']

        std = ta.STDDEV(am.close, volPeriod)
        atr = ta.ATR(am.high, am.low, am.close, volPeriod)
        rangeHL = ta.MAX(am.high, volPeriod)-ta.MIN(am.low, volPeriod)
        minVol = min(std[-1], atr[-1], rangeHL[-1])
        lowFilterRange = am.close[-1]*lowVolThreshold
        filterCanTrade = 1 if (minVol >= lowFilterRange) else -1
        return filterCanTrade

    #### 计算ADX指标
    def adxEnv(self,am,paraDict):
        adxPeriod = paraDict['adxPeriod']
        adxMaType = paraDict['adxMaType']
        adxMaPeriod = paraDict['adxMaPeriod']
        adxThreshold = paraDict['adxThreshold']

        adxTrend = ta.ADX(am.high, am.low, am.close, adxPeriod)
        adxMa = ta.MA(adxTrend, adxMaPeriod, matype=adxMaType)

        # Status
        adxCanTrade = True if (adxTrend[-1] > adxMa[-1]) and (adxTrend[-1]>=adxThreshold) else False

        return adxCanTrade, adxTrend, adxMa

    ### 计算ER指标
    def erAdd(self, am, paraDict):
        changeVolatilityPeriod = paraDict['changeVolatilityPeriod']
        erSemaPeriod = paraDict['erSemaPeriod']
        erLemaPeriod = paraDict['erLemaPeriod']
        erthreshold = paraDict['erthreshold']
        np.seterr(divide='ignore',invalid='ignore') 
        # indicator
        change = np.abs(am.close[changeVolatilityPeriod:]-am.close[:-changeVolatilityPeriod])
        volatility = ta.SUM(np.abs(am.close[1:]-am.close[:-1]), changeVolatilityPeriod)
        er = change[-120:]/volatility[-120:]
        erSma = ta.EMA(er, erSemaPeriod)
        erLma = ta.MA(er, erLemaPeriod)

        # condition
        erUp = (erSma[-1]>erLma[-1])
        erthreshold = (erSma[-1]>erthreshold)

        erCanAddPos = True if erUp and erthreshold else False
        return erCanAddPos, erSma, erLma
