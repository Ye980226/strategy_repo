import talib as ta
import numpy as np
import pandas as pd

"""
将kdj策略需要用到的信号生成器抽离出来
"""

class adxDiSignal():

    def __init__(self):
        self.author = 'channel'
    
    #### 计算DI指标
    def diSignal(self,am, paraDict):
        diPeriod = paraDict['diPeriod']
        plusDi = ta.PLUS_DI(am.high, am.low, am.close, diPeriod)
        minusDi = ta.MINUS_DI(am.high, am.low, am.close, diPeriod)

        priceDirection =  1 if (plusDi[-1]>minusDi[-1]) else -1

        return priceDirection, plusDi, minusDi


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

    ### 计算MA指标
    def maSignal(self, am, paraDict):
        signalMaPeriod = paraDict["signalMaPeriod"]
        signalMaType = paraDict["signalMaType"]
        
        signalMa = ta.MA(am.close, signalMaPeriod, matype=signalMaType)

        if signalMa[-1]>signalMa[-3]:
            signalMaDirection = 1
        elif signalMa[-1]<signalMa[-3]:
            signalMaDirection = -1
        else:
            signalMaDirection = 0
        
        return signalMaDirection, signalMa

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

    def addTriangle(self, paraDict):
        posTime = paraDict['posTime']
        addVar = paraDict['addVar']
        initVar = paraDict['initVar']

        sp = 0
        if (posTime % 2) != 0:
            sp = int((posTime+1)/2)
        else:
            raise Exception("Invalid length!", posTime)
        result = [0] * posTime
        for i in range(1, sp):
            initVar += addVar
            result[i] = int(initVar)
        for i in range(sp, posTime):
            initVar -= addVar
            result[i] = int(initVar)
        return np.array(result)

    def addLotList(self, paraDict):
        posTime = paraDict['posTime']
        addVar = paraDict['addVar']
        initVar = paraDict['initVar']
        sign = paraDict['sign']

        result = [initVar] * posTime
        for i in range(1, posTime):
            addMultiplier = eval(f"initVar {sign} addVar")
            result[i] = addMultiplier
        return np.array(result)
        