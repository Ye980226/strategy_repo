import talib as ta
import numpy as np


class doubleBoll():

    def __init__(self):
        self.author = 'zong'

    
    # ----------------------------------------------------------------
    def BollingerBand_Divergence(self,barArray1, barArray2, paraDict):
        """
        sec1: base security
        sec2: intermarket security
        计算sec2相对于sec1的偏离，当得到偏离高于某个阈值并有向下趋势时（比如10~30）buy Sec2，
        当得到的阈值小于某个阈值（比如-10~-30）且有向上趋势时 sell Sec2 
        """
        Bollperiod = paraDict['Bollperiod']
        emaPeriod = paraDict['EMAperiod']
        def getSecBol(barArray,period):
            upper, _, lower = ta.BBANDS(barArray.close,period,nbdevdn=2,nbdevup=2)
            return 1+(barArray.close-lower)/(upper-lower)

        secBol1 = getSecBol(barArray1,Bollperiod)
        secBol2 = getSecBol(barArray2,Bollperiod)
        divergence = ta.EMA(100*(secBol1-secBol2)/(secBol2),emaPeriod)
        return divergence