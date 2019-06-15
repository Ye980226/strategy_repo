import talib as ta
import numpy as np
import pandas as pd

class candleSignal():

    def __init__(self):
        self.author = 'sky'

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
        price_destinate = 0
        volumeMaPeriod = paraDict['volumeMaPeriod']
        volumeStdMultiple = paraDict['volumeStdMultiple']
        volumeMultiple = paraDict['volumeMultiple']
        range_ = paraDict['range_'] 
        volumeUpper, volumeClose, volumeLower = ta.BBANDS(am.volume[:-1], volumeMaPeriod, volumeStdMultiple, volumeStdMultiple)
        volumeSpike = 1 if am.volume[-1]>=volumeUpper[-1] else -1

        """
        last two bar is up &&  close[-1]>close[-2] && k_body_pct_change > pct
        """
        if (self.is_positive(am,1) and self.is_positive(am,2) and self.positive(am) and self.amp_positive(am,1,range_) and self.amp_positive(am,2,range_)):
            price_destinate = 1
        elif (self.is_negative(am,1) and self.is_negative(am,2) and self.negative(am) and self.amp_negative(am,1,range_) and self.amp_negative(am,2,range_)):
            price_destinate = -1
        """
        上两个bar均上涨，价格波幅与量的波幅比例
        """
        PriceRate = (am.close[-1]-am.open[-1])/(am.close[-2]-am.open[-2])
        volumeRate = am.volume[-1]/am.volume[-2]

        vol_Price = 0
        if abs(PriceRate)<volumeRate*volumeMultiple:
            if price_destinate==1:
                vol_Price = 1 
            elif price_destinate==-1:
                vol_Price = -1
            else:
                vol_Price = 0
        return volumeSpike, volumeUpper,vol_Price

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

    def positive(self,am,n=0):
        """返回某根K线相对上根k线是上升的"""
        return am.close[-1-n]>am.close[-2-n]
        
    def negative(self,am,n=0):
        """返回某根K线相对上根k线是下降的"""
        return am.close[-1-n]<am.close[-2-n]

    def amp_positive(self,am,n=1,_range=0):
        """K线body pct_change"""     
        return (am.close[-n]/am.open[-n]-1) >= _range
    
    def amp_negative(self,am,n=1,_range=0):
        """K线body pct_change""" 
        return (am.open[-n]/am.close[-n]-1) >= _range
        
    def entityRate(self, am, n=1):
        if self.checkCandle(am, n=1):
            return abs(am.open[-n] - am.close[-n]) / (am.high[-n] - am.low[-n])
        else:
            return 0


    # 爆拉时候不反方向开仓
    # 同方向遇到爆拉的，移动止盈止损
    def RocSignal(self,am,paraDict):
        rocperiod = paraDict['rocperiod']
        Roc_Value = paraDict['Roc_Value']
        Roc_MoM = paraDict['Roc_MoM']
        Roc = ta.ROC(am.close,rocperiod)
        if abs(Roc[-1])<Roc_Value:
            RocValue = 1
        else:
            RocValue = 0
        if Roc[-1] > Roc_MoM:
            Roc_stay=1
        elif Roc[-1] < -Roc_MoM:
            Roc_stay = -1
        else:
            Roc_stay = 0
        return RocValue,Roc,Roc_Value,Roc_stay



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





        