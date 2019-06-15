import talib as ta
import numpy as np
import pandas as pd

"""
将kdj策略需要用到的信号生成器抽离出来
"""

class candleSignal():

    def __init__(self):
        self.author = 'channel'

    ### 计算MA指标
    def rsiSignal(self, am, paraDict):
        rsiPeriod = paraDict["rsiPeriod"]
        rsiUpThreshold = paraDict["rsiUpThreshold"]
        rsiDnThreshold = paraDict["rsiDnThreshold"]
        rsi = ta.RSI(am.close, rsiPeriod)

        rsiStatus = 0
        if rsi[-1]>=rsiUpThreshold:
            rsiStatus = -1
        elif rsi[-1]<=rsiDnThreshold:
            rsiStatus = 1
        return rsiStatus, rsi

    def volumeSignal(self, am, paraDict):
        volumeMaPeriod = paraDict['volumeMaPeriod']
        volumeStdMultiple = paraDict['volumeStdMultiple']
        volumeUpper, volumeClose, volumeLower = ta.BBANDS(am.volume[:-1], volumeMaPeriod, volumeStdMultiple, volumeStdMultiple)

        volumeSpike = 1 if am.volume[-1]>=volumeUpper[-1] else -1
        return volumeSpike, volumeUpper

    def checkCandle(self,am, n=2):
        """"用于检查k线数目，要求array中已存在的大于n数目的k线"""
        if am.close[-n]!=0:
            return True
        else:
            return False
    
    def is_positive(self, am, n=1):
        """返回True代表过去的第n根k线是上升的"""
        return am.open[-n] < am.close[-n]

    def is_negative(self, am, n=1):
        """返回True代表过去的第n根k线是下降的"""
        return am.open[-n] > am.close[-n]

    def entityRate(self, am, n=1):
        if self.checkCandle(am, n=1):
            return abs(am.open[-n] - am.close[-n]) / (am.high[-n] - am.low[-n])
        else:
            return 0
    #############两根bar#################
    # 吞噬： 最近的一根Bar高低价与开收价都吞噬前一根Bar
    def candleEngulfing(self, am, paraDict):
        preMinBarPct = paraDict['preMinBarPct']
        postMinBarPct = paraDict['postMinBarPct']
        # preMinBarPct=0.008, postMinBarPct = 0.01
        """返回1看涨吞噬先跌后涨，返回-1看跌吞噬先涨后跌"""
        prePositive = self.is_positive(am, n=2)
        preNegative = self.is_negative(am, n=2)
        higherHigh = am.high[-1] > am.high[-2]
        lowerLow = am.low[-1] < am.low[-2]
        candleStatus = 0
        if higherHigh and lowerLow:
            if preNegative:
                preShort = am.open[-2]/am.close[-2]
                postLong = am.close[-1]/am.open[-1]
                candleStatus = 1 if preShort>=preMinBarPct and postLong>=postMinBarPct else 0
            elif prePositive:
                preLong = am.close[-2]/am.open[-2]
                postShort = am.open[-1]/am.close[-1]
                candleStatus = -1 if preLong>=preMinBarPct and postShort>=postMinBarPct else 0
        return candleStatus

    # 锤头(下影线长度为实体的2倍，设置一般为实体长度较小介于中线实体与小线实体之间)
    def candleHammer(self, am, paraDict):
        """返回1收阳线，返回-1收阴线"""
        # minShadowPct=0.005
        minShadowPct = paraDict['minShadowPct']
        entityMultiple = paraDict['entityMultiple']

        entity = self.entityRate(am)
        candleStatus = 0
        if self.is_positive(am):
            uplineRate = (am.high[-1]-am.close[-1])/(am.high[-1]-am.low[-1])
            downlineRate = (am.open[-1]-am.low[-1])/(am.high[-1]-am.low[-1])
            candleStatus = 1 if downlineRate>=entityMultiple*entity and uplineRate<=minShadowPct else 0
        elif self.is_negative(am):
            uplineRate = (am.high[-1]-am.open[-1])/(am.high[-1]-am.low[-1])
            downlineRate = (am.close[-1]-am.low[-1])/(am.high[-1]-am.low[-1])
            candleStatus = -1 if downlineRate>=entityMultiple*entity and uplineRate<=minShadowPct else 0
        return candleStatus

    # 倒锤头(上影线长度为实体的两倍以上，设置实体较小，下影线较短或者没有)
    def candleInvertedHammer(self, am, paraDict):
        """返回1收阳线，返回-1收阴线"""
        # minShadowPct=0.005
        minShadowPct = paraDict['minShadowPct']
        entityMultiple = paraDict['entityMultiple']

        entity = self.entityRate(am)
        candleStatus = 0
        if self.is_positive(am):
            uplineRate = (am.high[-1] - am.close[-1]) / (am.high[-1] - am.low[-1])
            downlineRate = (am.open[-1] - am.low[-1]) / (am.high[-1] - am.low[-1])
            candleStatus = 1 if uplineRate>=entityMultiple*entity and downlineRate<=minShadowPct else 0
        elif self.is_negative(am):
            uplineRate = (am.high[-1] - am.open[-1]) / (am.high[-1] - am.low[-1])
            downlineRate = (am.close[-1] - am.low[-1]) / (am.high[-1] - am.low[-1])
            candleStatus = -1 if uplineRate>=entityMultiple*entity and downlineRate<=minShadowPct else 0
        return candleStatus
    
    def candleSignal(self, am, paraDict):
        hlPct = paraDict['hlPct']
        cPct = paraDict['cPct']
        higherHigh = ((am.high[-1]/am.high[-2]-1)>hlPct)
        lowerClose = ((am.close[-2]/am.close[-1]-1)>cPct)
        lowerLow = ((am.low[-2]/am.low[-1]-1)>hlPct)
        higherClose = ((am.close[-1]/am.close[-2]-1)>cPct)
        candleDirection = 0
        if higherHigh and lowerClose:
            candleDirection = -1
        elif lowerLow and higherClose:
            candleDirection = 1
        else:
            candleDirection = 0
        return candleDirection

    def totalCandle(self, am, paraDict):
        candleDirection = 0
        candleSignal = self.candleSignal(am, paraDict)
        candleInvertedHammer = self.candleInvertedHammer(am, paraDict)
        candleHammer = self.candleHammer(am, paraDict)
        if candleSignal==1 or candleHammer!=0:
            candleDirection = 1
        elif candleSignal==-1 or candleInvertedHammer!=0:
            candleDirection = -1
        else:
            candleDirection = 0
        return candleDirection
    
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





        