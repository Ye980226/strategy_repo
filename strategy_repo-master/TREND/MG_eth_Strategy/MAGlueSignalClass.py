import talib as ta
import numpy as np
import pandas as pd

"""
将kdj策略需要用到的信号生成器抽离出来
"""

class MAGlueSignal():

    def __init__(self):
        self.author = 'sky'

### 计算MA指标
    def maSignal(self, am, paraDict):
        SMaPeriod = paraDict["SMaPeriod"]
        LMaPeriod = paraDict["LMaPeriod"]
        signalMaType = paraDict["signalMaType"]
        #双上就加仓
        SMa = ta.MA(am.close, SMaPeriod)
        LMa = ta.MA(am.close,LMaPeriod,matype=signalMaType)

        if SMa[-3]<LMa[-3] and SMa[-1]>LMa[-1]:
            signalMaDirection = 1
        elif SMa[-3]>LMa[-3] and SMa[-1]<LMa[-1]:
            signalMaDirection = -1
        else:
            signalMaDirection = 0
        return signalMaDirection,SMa,LMa


    def Glue_Signal(self, am, paraDict):

        Window1 = paraDict['Window1']
        Window2 = paraDict['Window2']
        Window3 = paraDict['Window3']
        Window4 = paraDict['Window4']
        agg_throld = paraDict['agg_throld']
        back_bar = paraDict['back_bar']
        stay_bar = paraDict['stay_bar']
        Ma1 = ta.KAMA(am.close, Window1)
        Ma2 = ta.KAMA(am.close, Window2)
        Ma3 = ta.KAMA(am.close, Window3)
        Ma4 = ta.KAMA(am.close, Window4)
      
        maxarr = np.array([Ma1,Ma2,Ma3,Ma4]).max(0)
        minarr = np.array([Ma1,Ma2,Ma3,Ma4]).min(0)
        
        GlueSignal = 0
        
        agg_value = (maxarr/minarr-1)*100
        throld = np.mean(agg_value[-back_bar:-1])
        agg = np.insert(agg_value < throld,0,0)
        if np.sum(agg[-back_bar:]>0)>=stay_bar:
            maggClose = np.mean(am.close[-back_bar:])
            if am.close[-1]>maggClose:
                GlueSignal = 1
            elif am.close[-1]<maggClose:
                GlueSignal = -1

        return GlueSignal,agg_value,throld

    def rsiSignal(self, am, paraDict):
        rsiPeriod = paraDict["rsiPeriod"]
        rsiUpThreshold = paraDict["rsiUpThreshold"]
        rsiDnThreshold = paraDict["rsiDnThreshold"]
        rsi = ta.RSI(am.close, rsiPeriod)

        rsi_bottom = np.mean(100-rsi[rsi<45])
        rsi_top = np.mean(rsi[rsi>55])
        rsi_rate = rsi_bottom/rsi_top

        rsiStatus = 0
        if rsi[-1]>=rsiUpThreshold:
            rsiStatus = -1
        elif rsi[-1]<=rsiDnThreshold:
            rsiStatus = 1
        return rsiStatus, rsi,rsiUpThreshold,rsiDnThreshold,rsi_bottom,rsi_top,rsi_rate


    #### 计算ADX指标
    def AdxSignal(self,am,paraDict):
        adxPeriod = paraDict['adxPeriod']
        adxMaType = paraDict['adxMaType']
        adxMaPeriod = paraDict['adxMaPeriod']
        adxThreshold = paraDict['adxThreshold']

        adxTrend = ta.ADX(am.high, am.low, am.close, adxPeriod)
        adxMa = ta.MA(adxTrend, adxMaPeriod, matype=adxMaType)

        # Status
        adxCanTrade = True if (adxTrend[-1] > adxMa[-1]) and (adxTrend[-1]>=adxThreshold) else False

        return adxCanTrade, adxTrend, adxMa

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