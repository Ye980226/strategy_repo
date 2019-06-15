import talib as ta
import numpy as np  

class CalEnv():

    '用于存储不同的过滤方式'
    
    # -------------------------------
    def __init__(self):
        self.author = 'zongzong'

    # --------------------------------
    def highlowcheck(self, am, period=50, highlowMaxGap=0.2):
        """过去一段时间的最高价和最低价之差不允许超过一定幅度"""
        highlowNowGap = am.high[-period:].max()/am.low[-period:].min()-1
        if highlowNowGap > highlowMaxGap:
            return False
        else:
            return True

    # --------------------------------
    def atrcheck(self,am,period=50, atrShield=0.04):
        """要求当前的atr小于某个阈值并且在下降"""
        ATRSeries = ta.ATR(am.high, am.low,am.close,period) / am.close[-1]
        ATR = ATRSeries[-1]
        ATRMA = ta.MA(ATRSeries, period)
        if ATRMA[-1] > ATRMA[-2] or ATR > ATRMA[-1] or ATR > atrShield:
            return False
        else:
            return True

    # ---------------------------------
    def signalmacheck(self, am,longMaPeriod=40,period=50,magap=0.05):
        """用ma均线过滤"""
        longMA = ta.MA(am.close, longMaPeriod)
        mid = (am.high[-period:].max() + am.low[-period:].min()) / 2
        if max(longMA[-1], mid) / min(longMA[-1], mid) - 1 > magap:
            return False
        else:
            return True

    # ---------------------------------
    def doubluemacheck(self,am,shortMaPeriod=15,longMaPeriod=40,estimatehours=10, magap=0.02):
        """双均线粘合过滤"""
        shortMa = ta.MA(am.close,shortMaPeriod)
        longMa = ta.MA(am.close,longMaPeriod)
        for i in range(1,estimatehours+1):
            big = max(shortMa[i], longMa[i])
            small = min(shortMa[i], longMa[i])
            if big/small - 1>magap:
                return False
        return True

    # ---------------------------------
    def trendcheck(self,am,trendEmalen=120,sloplen=60,maxslope=0.01):
        """用斜率过滤"""
        EMA = ta.EMA(am.close, trendEmalen)[-trendEmalen:]
        K = ta.LINEARREG_SLOPE(EMA, sloplen)[-1]
        if abs(K) > maxslope:
            return False, K
        else:
            return True, K



    